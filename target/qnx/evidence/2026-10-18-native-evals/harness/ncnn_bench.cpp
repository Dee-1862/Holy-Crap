#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "net.h"

static bool read_file(const char *path, std::vector<unsigned char> &buffer)
{
    FILE *file = fopen(path, "rb");
    if (!file)
        return false;
    if (fseek(file, 0, SEEK_END) != 0)
    {
        fclose(file);
        return false;
    }
    const long length = ftell(file);
    if (length < 0 || fseek(file, 0, SEEK_SET) != 0)
    {
        fclose(file);
        return false;
    }
    buffer.resize((size_t)length);
    const bool success = length == 0 || fread(buffer.data(), 1, (size_t)length, file) == (size_t)length;
    fclose(file);
    return success;
}

static double percentile(const std::vector<double> &sorted, double fraction)
{
    if (sorted.empty())
        return NAN;
    const double position = (double)(sorted.size() - 1) * fraction;
    const size_t lower = (size_t)floor(position);
    const size_t upper = (size_t)ceil(position);
    if (lower == upper)
        return sorted[lower];
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - (double)lower);
}

int main(int argc, char **argv)
{
    if (argc < 9 || argc > 10)
    {
        fprintf(stderr, "usage: %s PARAM BIN INPUT_RAW SIZE ITERATIONS THREADS INPUT_BLOB OUTPUT_BLOB [calls.csv]\n", argv[0]);
        return 64;
    }
    const char *param_path = argv[1];
    const char *bin_path = argv[2];
    const char *input_path = argv[3];
    const int size = atoi(argv[4]);
    const int iterations = atoi(argv[5]);
    const int threads = atoi(argv[6]);
    const char *input_blob = argv[7];
    const char *output_blob = argv[8];
    const char *csv_path = argc == 10 ? argv[9] : NULL;
    if (size < 1 || iterations < 2 || iterations > 10000 || threads < 1 || threads > 4)
    {
        fprintf(stderr, "invalid size, iterations, or threads\n");
        return 64;
    }

    std::vector<unsigned char> bytes;
    if (!read_file(input_path, bytes))
    {
        fprintf(stderr, "cannot read input: %s\n", input_path);
        return 66;
    }
    const size_t count = (size_t)3 * (size_t)size * (size_t)size;
    if (bytes.size() != count * sizeof(float))
    {
        fprintf(stderr, "input size mismatch: got %zu, expected %zu bytes\n", bytes.size(), count * sizeof(float));
        return 65;
    }
    const float *values = reinterpret_cast<const float *>(bytes.data());
    for (size_t index = 0; index < count; ++index)
    {
        if (!std::isfinite(values[index]))
        {
            fprintf(stderr, "non-finite input value at %zu\n", index);
            return 65;
        }
    }

    ncnn::Net net;
    net.opt.num_threads = threads;
    net.opt.use_fp16_packed = false;
    net.opt.use_fp16_storage = false;
    net.opt.use_fp16_arithmetic = false;
    const auto load_started = std::chrono::steady_clock::now();
    if (net.load_param(param_path) != 0 || net.load_model(bin_path) != 0)
    {
        fprintf(stderr, "failed to load NCNN model\n");
        return 70;
    }
    const auto load_finished = std::chrono::steady_clock::now();
    const double load_ms = std::chrono::duration<double, std::milli>(load_finished - load_started).count();
    ncnn::Mat input(size, size, 3, (void *)values, sizeof(float));

    FILE *csv = NULL;
    if (csv_path)
    {
        csv = fopen(csv_path, "w");
        if (!csv)
        {
            perror("fopen calls.csv");
            return 73;
        }
        fprintf(csv, "call_index,cold_first_call,inference_ms,output_elements,output_finite\n");
    }

    std::vector<double> calls;
    calls.reserve((size_t)iterations);
    size_t output_elements = 0;
    bool all_finite = true;
    for (int iteration = 0; iteration < iterations; ++iteration)
    {
        ncnn::Extractor extractor = net.create_extractor();
        if (extractor.input(input_blob, input) != 0)
        {
            fprintf(stderr, "failed to set input blob %s\n", input_blob);
            if (csv)
                fclose(csv);
            return 70;
        }
        ncnn::Mat output;
        const auto started = std::chrono::steady_clock::now();
        const int extract_result = extractor.extract(output_blob, output);
        const auto finished = std::chrono::steady_clock::now();
        if (extract_result != 0)
        {
            fprintf(stderr, "failed to extract output blob %s\n", output_blob);
            if (csv)
                fclose(csv);
            return 70;
        }
        const double elapsed_ms = std::chrono::duration<double, std::milli>(finished - started).count();
        calls.push_back(elapsed_ms);
        output_elements = output.total();
        bool finite = output.elemsize == sizeof(float) && output.elempack == 1 && output_elements > 0;
        if (finite)
        {
            const float *output_values = (const float *)output.data;
            for (size_t index = 0; index < output_elements; ++index)
            {
                if (!std::isfinite(output_values[index]))
                {
                    finite = false;
                    break;
                }
            }
        }
        all_finite = all_finite && finite;
        if (csv)
            fprintf(csv, "%d,%s,%.6f,%zu,%s\n", iteration, iteration == 0 ? "true" : "false", elapsed_ms, output_elements, finite ? "true" : "false");
    }
    if (csv && fclose(csv) != 0)
    {
        perror("fclose calls.csv");
        return 74;
    }
    if (!all_finite)
    {
        fprintf(stderr, "output validation failed\n");
        return 70;
    }

    std::vector<double> steady(calls.begin() + 1, calls.end());
    std::sort(steady.begin(), steady.end());
    double steady_total = 0.0;
    for (size_t index = 0; index < steady.size(); ++index)
        steady_total += steady[index];
    printf("{\"tool\":\"ncnn_native_bench\",\"precision\":\"fp32\",\"size\":%d,\"threads\":%d,"
           "\"iterations\":%d,\"load_ms\":%.6f,\"cold_first_inference_ms\":%.6f,"
           "\"steady_ms\":{\"count\":%zu,\"mean\":%.6f,\"p50\":%.6f,\"p95\":%.6f,\"p99\":%.6f,\"max\":%.6f},"
           "\"output_elements\":%zu,\"output_finite\":true}\n",
           size, threads, iterations, load_ms, calls[0], steady.size(),
           steady_total / (double)steady.size(),
           percentile(steady, 0.50), percentile(steady, 0.95),
           percentile(steady, 0.99), steady.back(), output_elements);
    return 0;
}
