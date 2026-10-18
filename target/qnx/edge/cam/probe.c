/* Dump the raw camera_buffer_t the QNX camera library hands to a viewfinder callback.
   The SDP headers are not on the target, so the few calls we need are declared here by hand. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

typedef int32_t camera_handle_t;
typedef void (*vf_cb)(camera_handle_t, void *, void *);
extern int camera_open(int unit, uint32_t mode, camera_handle_t *h);
extern int camera_close(camera_handle_t h);
extern int camera_start_viewfinder(camera_handle_t h, vf_cb cb, void *status_cb, void *arg);
extern int camera_stop_viewfinder(camera_handle_t h);

static int count;
static void on_frame(camera_handle_t h, void *buf, void *arg) {
    (void)h; (void)arg;
    if (++count != 10) return;
    uint32_t w[40];
    memcpy(w, buf, sizeof w);
    printf("u32:");
    for (int i = 0; i < 40; i++) printf(" %u", w[i]);
    printf("\nu64 at 8: %llu  ptr at 16: %p\n", (unsigned long long)*(uint64_t *)((char *)buf + 8), *(void **)((char *)buf + 16));
    fflush(stdout);
}

int main(int argc, char **argv) {
    camera_handle_t h;
    int e = camera_open(argc > 1 ? atoi(argv[1]) : 1, 15, &h);
    printf("open %d\n", e);
    if (e) return 1;
    printf("start %d\n", camera_start_viewfinder(h, on_frame, NULL, NULL));
    fflush(stdout);
    sleep(2);
    printf("frames in 2 s: %d\n", count);
    camera_stop_viewfinder(h);
    camera_close(h);
    return 0;
}
