// Spin kernel used by the dummy worker to hold a GPU at ~100% utilization.
//
// The compiled PTX lives next to this file as kernel.ptx and is loaded at runtime
// through the CUDA driver API (cuModuleLoadData), which JIT-compiles it for whatever
// architecture the target GPU happens to be. That is why the worker needs nothing but
// libcuda.so.1 -- no CUDA toolkit, no torch, no pip packages on the deployed node.
//
// Regenerate with:
//   nvcc -arch=compute_75 -ptx kernel.cu -o kernel.ptx
//
// compute_75 is the lowest virtual architecture CUDA 13 still accepts; the driver JITs
// it forward to Turing and everything newer (A100 = sm_80, H100 = sm_90, ...).

extern "C" __global__ void spin(float *buf, unsigned long long iters)
{
    unsigned int tid = blockIdx.x * blockDim.x + threadIdx.x;

    // Two independent FMA chains keep the pipelines busy without going memory bound.
    float x = buf[tid];
    float y = x + 1.0f;

    for (unsigned long long i = 0; i < iters; ++i) {
        x = fmaf(x, 1.0000001f, 1e-7f);
        y = fmaf(y, 0.9999999f, 1e-7f);
    }

    // Write back so the compiler cannot eliminate the loop.
    buf[tid] = x + y;
}
