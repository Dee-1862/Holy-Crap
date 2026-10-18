/* A small C bridge to ONNX Runtime for Python's ctypes on the QNX Pi.
 *
 * QNX's onnxruntime 1.24.4 package (oss.qnx.com, 8.0.5 extra) ships libonnxruntime.so but its Python module is
 * missing the compiled pybind part, so Python cannot import it. This file wraps the few C API calls we need:
 * open a model, run one float input, copy back the first output and its shape. Build on the Pi:
 *
 *   clang -O2 -shared -fPIC hc_ort.c -I$HOME/ort-include -l:libonnxruntime.so.1 -o libhcort.so
 */
#include <onnxruntime_c_api.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const OrtApi *api;
static char last_error[512];

typedef struct {
  OrtEnv *env;
  OrtSession *sess;
  OrtMemoryInfo *mem;
  char in_name[128];
  char out_name[128];
} Handle;

/* Keeps the message of a failed call for hc_error() and reports failure. */
static int failed(OrtStatus *st) {
  if (!st) return 0;
  snprintf(last_error, sizeof last_error, "%s", api->GetErrorMessage(st));
  api->ReleaseStatus(st);
  return 1;
}

const char *hc_error(void) { return last_error; }

int hc_init(void) {
  api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
  return api ? 0 : -1;
}

void *hc_open(const char *path, int threads) {
  Handle *h = calloc(1, sizeof *h);
  OrtSessionOptions *so = NULL;
  OrtAllocator *al = NULL;
  char *name = NULL;
  if (!h || failed(api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "hc", &h->env))) goto fail;
  if (failed(api->CreateSessionOptions(&so))) goto fail;
  if (failed(api->SetIntraOpNumThreads(so, threads))) goto fail;
  if (failed(api->SetSessionGraphOptimizationLevel(so, ORT_ENABLE_ALL))) goto fail;
  if (failed(api->CreateSession(h->env, path, so, &h->sess))) goto fail;
  api->ReleaseSessionOptions(so);
  so = NULL;
  if (failed(api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &h->mem))) goto fail;
  if (failed(api->GetAllocatorWithDefaultOptions(&al))) goto fail;
  if (failed(api->SessionGetInputName(h->sess, 0, al, &name))) goto fail;
  snprintf(h->in_name, sizeof h->in_name, "%s", name);
  api->AllocatorFree(al, name);
  if (failed(api->SessionGetOutputName(h->sess, 0, al, &name))) goto fail;
  snprintf(h->out_name, sizeof h->out_name, "%s", name);
  api->AllocatorFree(al, name);
  return h;
fail:
  if (so) api->ReleaseSessionOptions(so);
  if (h) {
    if (h->sess) api->ReleaseSession(h->sess);
    if (h->env) api->ReleaseEnv(h->env);
    free(h);
  }
  return NULL;
}

/* Runs one input. Copies up to out_cap floats of the first output into out and its shape into out_shape
 * (up to 8 dims). Returns the number of output floats, or -1 on error. */
long hc_run(void *hp, const float *in, const int64_t *shape, int ndim, float *out, long out_cap,
            int64_t *out_shape, int *out_ndim) {
  Handle *h = hp;
  OrtValue *input = NULL, *output = NULL;
  OrtTensorTypeAndShapeInfo *info = NULL;
  long n = -1;
  size_t count = 1, dims = 0, total = 0;
  for (int i = 0; i < ndim; i++) count *= (size_t)shape[i];
  if (failed(api->CreateTensorWithDataAsOrtValue(h->mem, (void *)in, count * sizeof(float), shape, (size_t)ndim,
                                                 ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &input))) goto done;
  const char *ins[] = {h->in_name};
  const char *outs[] = {h->out_name};
  if (failed(api->Run(h->sess, NULL, ins, (const OrtValue *const *)&input, 1, outs, 1, &output))) goto done;
  if (failed(api->GetTensorTypeAndShape(output, &info))) goto done;
  if (failed(api->GetDimensionsCount(info, &dims))) goto done;
  if (dims > 8) dims = 8;
  if (failed(api->GetDimensions(info, out_shape, dims))) goto done;
  *out_ndim = (int)dims;
  if (failed(api->GetTensorShapeElementCount(info, &total))) goto done;
  float *data = NULL;
  if (failed(api->GetTensorMutableData(output, (void **)&data))) goto done;
  n = (long)total < out_cap ? (long)total : out_cap;
  memcpy(out, data, (size_t)n * sizeof(float));
done:
  if (info) api->ReleaseTensorTypeAndShapeInfo(info);
  if (output) api->ReleaseValue(output);
  if (input) api->ReleaseValue(input);
  return n;
}

void hc_close(void *hp) {
  Handle *h = hp;
  if (!h) return;
  api->ReleaseMemoryInfo(h->mem);
  api->ReleaseSession(h->sess);
  api->ReleaseEnv(h->env);
  free(h);
}
