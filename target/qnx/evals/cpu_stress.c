#define _POSIX_C_SOURCE 200809L

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static uint64_t monotonic_ns(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0)
        return 0;
    return (uint64_t)value.tv_sec * UINT64_C(1000000000) + (uint64_t)value.tv_nsec;
}

int main(int argc, char **argv)
{
    if (argc != 2)
    {
        fprintf(stderr, "usage: %s DURATION_SECONDS\n", argv[0]);
        return 64;
    }
    const double duration = strtod(argv[1], NULL);
    if (!(duration > 0.0 && duration <= 600.0))
    {
        fprintf(stderr, "duration must be in (0, 600]\n");
        return 64;
    }
    const uint64_t started = monotonic_ns();
    const uint64_t end = started + (uint64_t)(duration * 1000000000.0);
    volatile uint64_t state = UINT64_C(0x9e3779b97f4a7c15);
    uint64_t iterations = 0;
    while (monotonic_ns() < end)
    {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        ++iterations;
    }
    printf("{\"tool\":\"bounded_cpu_stress\",\"pid\":%ld,\"duration_s\":%.6f,\"iterations\":%" PRIu64 ",\"checksum\":%" PRIu64 "}\n",
           (long)getpid(), (double)(monotonic_ns() - started) / 1000000000.0, iterations, state);
    return 0;
}
