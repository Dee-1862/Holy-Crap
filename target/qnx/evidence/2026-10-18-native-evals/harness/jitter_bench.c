#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static uint64_t ns(const struct timespec *value)
{
    return (uint64_t)value->tv_sec * UINT64_C(1000000000) + (uint64_t)value->tv_nsec;
}

static struct timespec from_ns(uint64_t value)
{
    struct timespec result;
    result.tv_sec = (time_t)(value / UINT64_C(1000000000));
    result.tv_nsec = (long)(value % UINT64_C(1000000000));
    return result;
}

static int compare_double(const void *left, const void *right)
{
    const double a = *(const double *)left;
    const double b = *(const double *)right;
    return (a > b) - (a < b);
}

static double percentile(const double *sorted, size_t count, double fraction)
{
    if (count == 0)
        return NAN;
    const double position = (double)(count - 1) * fraction;
    const size_t lower = (size_t)floor(position);
    const size_t upper = (size_t)ceil(position);
    if (lower == upper)
        return sorted[lower];
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - (double)lower);
}

static const char *policy_name(int policy)
{
    switch (policy)
    {
    case SCHED_FIFO:
        return "fifo";
    case SCHED_RR:
        return "round_robin";
    case SCHED_OTHER:
        return "other";
    default:
        return "unknown";
    }
}

int main(int argc, char **argv)
{
    if (argc < 4 || argc > 5)
    {
        fprintf(stderr, "usage: %s ITERATIONS PERIOD_US DEADLINE_US [raw.csv]\n", argv[0]);
        return 64;
    }

    const long iterations_long = strtol(argv[1], NULL, 10);
    const long period_us = strtol(argv[2], NULL, 10);
    const long deadline_us = strtol(argv[3], NULL, 10);
    if (iterations_long < 2 || period_us < 1 || deadline_us < 0)
    {
        fprintf(stderr, "invalid numeric argument\n");
        return 64;
    }
    const size_t iterations = (size_t)iterations_long;
    double *lateness_us = calloc(iterations, sizeof(*lateness_us));
    if (!lateness_us)
    {
        perror("calloc");
        return 70;
    }

    FILE *raw = NULL;
    if (argc == 5)
    {
        raw = fopen(argv[4], "w");
        if (!raw)
        {
            perror("fopen raw.csv");
            free(lateness_us);
            return 73;
        }
        fprintf(raw, "iteration,target_monotonic_ns,observed_monotonic_ns,lateness_us,deadline_miss\n");
    }

    int policy = -1;
    struct sched_param parameter;
    memset(&parameter, 0, sizeof(parameter));
    if (pthread_getschedparam(pthread_self(), &policy, &parameter) != 0)
    {
        perror("pthread_getschedparam");
        if (raw)
            fclose(raw);
        free(lateness_us);
        return 70;
    }

    struct timespec current;
    if (clock_gettime(CLOCK_MONOTONIC, &current) != 0)
    {
        perror("clock_gettime");
        if (raw)
            fclose(raw);
        free(lateness_us);
        return 70;
    }
    uint64_t target_ns = ns(&current) + UINT64_C(100000000);
    const uint64_t period_ns = (uint64_t)period_us * UINT64_C(1000);
    size_t misses = 0;
    double total = 0.0;

    for (size_t index = 0; index < iterations; ++index)
    {
        target_ns += period_ns;
        const struct timespec target = from_ns(target_ns);
        int result;
        do
        {
            result = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, NULL);
        } while (result == EINTR);
        if (result != 0)
        {
            errno = result;
            perror("clock_nanosleep");
            if (raw)
                fclose(raw);
            free(lateness_us);
            return 70;
        }
        if (clock_gettime(CLOCK_MONOTONIC, &current) != 0)
        {
            perror("clock_gettime");
            if (raw)
                fclose(raw);
            free(lateness_us);
            return 70;
        }
        const uint64_t observed_ns = ns(&current);
        const double late = observed_ns >= target_ns
                                ? (double)(observed_ns - target_ns) / 1000.0
                                : -((double)(target_ns - observed_ns) / 1000.0);
        lateness_us[index] = late;
        total += late;
        const int miss = late > (double)deadline_us;
        misses += (size_t)miss;
        if (raw)
            fprintf(raw, "%zu,%" PRIu64 ",%" PRIu64 ",%.3f,%d\n", index, target_ns, observed_ns, late, miss);
    }
    if (raw && fclose(raw) != 0)
    {
        perror("fclose raw.csv");
        free(lateness_us);
        return 74;
    }

    qsort(lateness_us, iterations, sizeof(*lateness_us), compare_double);
    printf("{\"tool\":\"qnx_jitter_bench\",\"pid\":%ld,\"clock\":\"CLOCK_MONOTONIC\","
           "\"iterations\":%zu,\"period_us\":%ld,\"deadline_us\":%ld,"
           "\"scheduler_policy\":\"%s\",\"scheduler_policy_id\":%d,\"priority\":%d,"
           "\"lateness_us\":{\"mean\":%.3f,\"p50\":%.3f,\"p95\":%.3f,\"p99\":%.3f,\"max\":%.3f},"
           "\"deadline_misses\":%zu,\"deadline_miss_rate\":%.9f}\n",
           (long)getpid(), iterations, period_us, deadline_us,
           policy_name(policy), policy, parameter.sched_priority,
           total / (double)iterations,
           percentile(lateness_us, iterations, 0.50),
           percentile(lateness_us, iterations, 0.95),
           percentile(lateness_us, iterations, 0.99),
           lateness_us[iterations - 1], misses, (double)misses / (double)iterations);
    free(lateness_us);
    return 0;
}

