"""Machine learning: return routing (PyTorch) and prioritization (XGBoost).

Both libraries use OpenMP to spread work across CPU cores, and each can load a *different*
copy of the OpenMP runtime (PyTorch bundles its own; XGBoost uses the system's). On macOS,
two copies running thread pools in the same process crash it with a segmentation fault.

The models here are small, so they run single-threaded: training still takes seconds,
prediction takes microseconds, and in a web server with several worker processes, one thread
per model avoids workers fighting over CPU cores anyway. This must run before torch or
xgboost is imported, so it lives in the package's __init__.
"""

import os

ML_THREADS = 1
os.environ.setdefault("OMP_NUM_THREADS", str(ML_THREADS))

import torch  # noqa: E402

torch.set_num_threads(ML_THREADS)
