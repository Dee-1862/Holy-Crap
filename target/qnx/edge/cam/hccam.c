/* hccam: live camera section of the Holy-Crap edge pipeline on QNX.

   Two threads, no frame queue:
   - the camera library's callback thread copies every full resolution frame into a ring of slots in
     shared memory (/dev/shmem/hc-frames). It never waits for anyone, so the newest frame is always there
     and nothing piles up behind a slow reader.
   - a worker thread wakes at the target rate, takes the newest slot, cuts it down to a small grey frame
     and sends that to the spot finder by QNX message passing (name hc/spotter), with the slot and
     sequence number, so later sections can cut a full resolution patch out of shared memory themselves.

   The QNX SDP camera headers are not on the target image, so the few calls used are declared here. The
   frame description offsets were read from a live frame (cam/probe.c) for both cameras on this Pi and are checked on every
   frame, a frame that does not match is skipped and counted.

   cc -O2 -o hccam hccam.c -lcamapi
   hccam [-u unit] [-r rate] [-w small_width] [-c copy_rate]

   -c caps how many full frames a second are copied into shared memory (default 8, 0 = every frame). The sensor
   delivers 30 a second but the pipeline reads at most a few (spot finder 2, live view 4), so copying all 30 only
   costs memory bandwidth. Frames that are copied are untouched, so detection sees the same pixels.          */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/dispatch.h>
#include <sys/mman.h>
#include <sys/neutrino.h>
#include <time.h>
#include <unistd.h>

typedef int32_t camera_handle_t;
typedef void (*vf_cb)(camera_handle_t, void *, void *);
extern int camera_open(int unit, uint32_t mode, camera_handle_t *h);
extern int camera_close(camera_handle_t h);
extern int camera_start_viewfinder(camera_handle_t h, vf_cb cb, void *status_cb, void *arg);
extern int camera_stop_viewfinder(camera_handle_t h);

#define SLOTS 4
#define MAX_W 2304
#define MAX_H 1296
#define FRAME_BYTES (MAX_W * MAX_H * 4)            /* room for 4 bytes a pixel */
#define TYPE_YUV422 14                             /* the test pattern camera, unit 1 */
#define TYPE_RGB32 31                              /* the Camera Module 3 in an RGB setup, bytes B G R A */
#define TYPE_NV12 1                                /* the Camera Module 3 as configured now (unit 4): luma plane, then
                                                      half height interleaved U V plane */
#define MSG_TYPE 0x4843                            /* same message type as qnxipc.py */

/* Shared memory layout, read by Python (target/qnx/edge/shm.py). Keep in step. */
struct slot_head {
    _Atomic uint64_t seq;                          /* odd while being written, even when complete */
    uint32_t width, height, stride, frametype;
    int64_t time_ns;
    uint8_t pad[32];
};
struct ring {
    uint32_t magic, slots, frame_bytes, newest;    /* magic 'HCF1' */
    uint64_t frames, skipped;
    uint8_t pad[40];
    struct slot_head head[SLOTS];
};
#define DATA(r, i) ((uint8_t *)(r) + 4096 + (size_t)(i) * FRAME_BYTES)

static struct ring *ring;
static volatile sig_atomic_t stop;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t fresh = PTHREAD_COND_INITIALIZER;
static int y_offset = -1;                          /* 0 for YUYV, 1 for UYVY, found from the first frames */
static double copy_rate = 8.0;                     /* full frames a second copied to shared memory, 0 = all */
static _Atomic uint64_t not_copied;                /* frames the camera gave that we let go by (-c) */

static int64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_REALTIME, &t);
    return (int64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

/* Camera thread. Offsets from the probe: frametype at 0, buffer pointer at 16, height, width, stride at 72,
   and for NV12 the U V plane offset at 88 and its stride at 96. NV12 is kept as it is, luma rows then U V rows,
   stored with stride = width so readers find the U V plane right after width x height luma bytes. */
static void on_frame(camera_handle_t h, void *buf, void *arg) {
    (void)h; (void)arg;
    if (copy_rate > 0) {                           /* only the frames someone will read: skip the 4.5 MB copy otherwise */
        static int64_t last_copy;
        int64_t t = now_ns();
        if (t - last_copy < (int64_t)(1e9 / copy_rate)) {
            not_copied++;
            return;
        }
        last_copy = t;
    }
    const uint8_t *b = buf;
    uint32_t type = *(const uint32_t *)b;
    const uint8_t *pix = *(uint8_t *const *)(b + 16);
    uint32_t height = *(const uint32_t *)(b + 72), width = *(const uint32_t *)(b + 76), stride = *(const uint32_t *)(b + 80);
    int nv12 = type == TYPE_NV12;
    uint32_t bpp = type == TYPE_RGB32 ? 4 : type == TYPE_YUV422 ? 2 : nv12 ? 1 : 0;
    uint32_t uv_off = nv12 ? *(const uint32_t *)(b + 88) : 0, uv_stride = nv12 ? *(const uint32_t *)(b + 96) : 0;
    if (!pix || !bpp || width == 0 || width > MAX_W || height == 0 || height > MAX_H || stride < width * bpp ||
        (nv12 && (uv_stride < width || uv_off < stride * height))) {
        ring->skipped++;
        return;
    }
    uint32_t i = (ring->newest + 1) % SLOTS;
    struct slot_head *s = &ring->head[i];
    atomic_fetch_add(&s->seq, 1);                  /* now odd: readers know it is changing */
    for (uint32_t y = 0; y < height; y++)
        memcpy(DATA(ring, i) + (size_t)y * width * bpp, pix + (size_t)y * stride, width * bpp);
    if (nv12)
        for (uint32_t y = 0; y < height / 2; y++)
            memcpy(DATA(ring, i) + (size_t)(height + y) * width, pix + uv_off + (size_t)y * uv_stride, width);
    s->width = width; s->height = height; s->stride = width * bpp; s->frametype = type; s->time_ns = now_ns();
    atomic_fetch_add(&s->seq, 1);                  /* even again: complete */
    pthread_mutex_lock(&lock);
    ring->newest = i;
    ring->frames++;
    pthread_cond_signal(&fresh);
    pthread_mutex_unlock(&lock);
}

/* In YUV 4:2:2 the luma bytes vary much more than the chroma bytes, which sit near 128. */
static int find_y_offset(const uint8_t *p, uint32_t n) {
    double v[2] = {0, 0};
    for (uint32_t k = 0; k + 1 < n; k += 2) {
        v[0] += (p[k] - 128.0) * (p[k] - 128.0);
        v[1] += (p[k + 1] - 128.0) * (p[k + 1] - 128.0);
    }
    return v[1] > v[0];
}

/* Worker thread: newest frame, cut down to small grey, sent to the spot finder. */
static void *worker(void *arg) {
    double rate = *(double *)arg;
    int sw = *((int *)arg + 2);
    int coid = -1;
    uint8_t *msg = malloc(65536 + 1024);
    uint64_t sent = 0, dropped = 0;
    struct timespec next;
    clock_gettime(CLOCK_MONOTONIC, &next);
    while (!stop) {
        pthread_mutex_lock(&lock);
        while (ring->frames == 0 && !stop) pthread_cond_wait(&fresh, &lock);
        uint32_t i = ring->newest;
        pthread_mutex_unlock(&lock);
        struct slot_head *s = &ring->head[i];
        uint64_t seq = atomic_load(&s->seq);
        uint32_t w = s->width, h = s->height;
        int sh = (int)((int64_t)sw * h / w), step = w / sw;
        int rgb = s->frametype == TYPE_RGB32, nv12 = s->frametype == TYPE_NV12;
        if (!rgb && !nv12 && y_offset < 0) y_offset = find_y_offset(DATA(ring, i), w * 2 * 8);
        /* header JSON then grey pixels, the same message camera.py sends */
        char head[512];
        int n = snprintf(head, sizeof head,
                         "{\"k\":%llu,\"w\":%d,\"h\":%d,\"t\":%.3f,\"dropped\":%llu,\"slot\":%u,\"seq\":%llu,"
                         "\"fullW\":%u,\"fullH\":%u,\"shm\":\"/dev/shmem/hc-frames\",\"source\":\"camera\"}",
                         (unsigned long long)sent, sw, sh, s->time_ns / 1e9, (unsigned long long)dropped, i,
                         (unsigned long long)seq, w, h);
        msg[0] = MSG_TYPE & 0xff; msg[1] = MSG_TYPE >> 8; msg[2] = msg[3] = 0;
        uint32_t len = 2 + n + sw * sh;
        memcpy(msg + 4, &len, 4);
        msg[8] = n & 0xff; msg[9] = n >> 8;
        memcpy(msg + 10, head, n);
        uint8_t *g = msg + 10 + n;
        const uint8_t *src = DATA(ring, i);
        for (int y = 0; y < sh; y++)                /* box filter: average step by step luma samples */
            for (int x = 0; x < sw; x++) {
                unsigned sum = 0;
                for (int dy = 0; dy < step; dy++) {
                    if (rgb) {                          /* luma from B G R */
                        const uint8_t *row = src + (size_t)(y * step + dy) * w * 4;
                        for (int dx = 0; dx < step; dx++) {
                            const uint8_t *q = row + (x * step + dx) * 4;
                            sum += (29 * q[0] + 150 * q[1] + 77 * q[2]) >> 8;
                        }
                    } else if (nv12) {                  /* luma plane, one byte a pixel */
                        const uint8_t *row = src + (size_t)(y * step + dy) * w;
                        for (int dx = 0; dx < step; dx++) sum += row[x * step + dx];
                    } else {
                        const uint8_t *row = src + (size_t)(y * step + dy) * w * 2 + y_offset;
                        for (int dx = 0; dx < step; dx++) sum += row[(x * step + dx) * 2];
                    }
                }
                g[y * sw + x] = sum / (step * step);
            }
        if (atomic_load(&s->seq) != seq) dropped++;   /* overwritten while reading, very rare at 4 slots */
        if (coid < 0) coid = name_open("hc/spotter", 0);
        char reply[256];
        if (coid < 0 || MsgSend(coid, msg, 8 + len, reply, sizeof reply) < 0) {
            dropped++;
            if (coid >= 0) { name_close(coid); coid = -1; }
        } else {
            sent++;
        }
        next.tv_nsec += (long)(1e9 / rate);
        while (next.tv_nsec >= 1000000000) { next.tv_nsec -= 1000000000; next.tv_sec++; }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL);
    }
    free(msg);
    return NULL;
}

static void on_signal(int s) { (void)s; stop = 1; pthread_cond_broadcast(&fresh); }

int main(int argc, char **argv) {
    int unit = 2, opt;
    struct { double rate; int sw; } cfg = {2.0, 320};
    while ((opt = getopt(argc, argv, "u:r:w:c:")) != -1) {
        if (opt == 'u') unit = atoi(optarg);
        else if (opt == 'r') cfg.rate = atof(optarg);
        else if (opt == 'w') cfg.sw = atoi(optarg);
        else if (opt == 'c') copy_rate = atof(optarg);
    }
    size_t bytes = 4096 + (size_t)SLOTS * FRAME_BYTES;
    shm_unlink("/hc-frames");
    int fd = shm_open("/hc-frames", O_RDWR | O_CREAT, 0644);
    if (fd < 0 || ftruncate(fd, bytes) < 0) { perror("shm"); return 1; }
    ring = mmap(NULL, bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (ring == MAP_FAILED) { perror("mmap"); return 1; }
    memset(ring, 0, 4096);
    ring->magic = 0x31464348; ring->slots = SLOTS; ring->frame_bytes = FRAME_BYTES;
    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);

    camera_handle_t h;
    int e = camera_open(unit, 15, &h);
    if (e) { fprintf(stderr, "camera_open unit %d failed: %d\n", unit, e); return 2; }
    if (copy_rate > 0 && copy_rate < cfg.rate) copy_rate = cfg.rate;   /* never copy less often than the worker reads */
    pthread_t t;
    pthread_create(&t, NULL, worker, &cfg);
    pthread_setname_np(t, "hccam-worker");
    e = camera_start_viewfinder(h, on_frame, NULL, NULL);
    if (e) { fprintf(stderr, "camera_start_viewfinder failed: %d\n", e); return 3; }
    printf("hccam: unit %d, %.1f frames a second to hc/spotter at %d wide, full frames in /dev/shmem/hc-frames, "
           "copying at most %.1f a second\n", unit, cfg.rate, cfg.sw, copy_rate);
    fflush(stdout);
    for (int tick = 0; !stop; tick++) {
        sleep(1);
        if (tick % 30 == 29) {                     /* every 30 s, for benchmarking: copied vs let go */
            printf("hccam: copied %llu, let go %llu, bad %llu\n", (unsigned long long)ring->frames,
                   (unsigned long long)not_copied, (unsigned long long)ring->skipped);
            fflush(stdout);
        }
    }
    camera_stop_viewfinder(h);
    camera_close(h);
    pthread_join(t, NULL);
    shm_unlink("/hc-frames");
    return 0;
}
