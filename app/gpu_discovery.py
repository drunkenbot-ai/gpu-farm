"""GPU discovery & validation (goals.md section 3: "GPU Discovery & Validation").

Detects every GPU visible on a machine along with the hardware/runtime
details the farm needs for scheduling and health display -- name, vendor,
VRAM, CUDA support/version, compute capability, driver version, PCI ID,
utilization, temperature, and power draw -- then validates each GPU against
the farm's minimum join requirements:

    * NVIDIA GPU
    * CUDA supported
    * Minimum 4 GB VRAM
    * Healthy CUDA runtime
    * Compatible driver

Only GPUs that pass validation are eligible to join the farm as trainable
resources (goals.md section 3 + section 4 "GPU Selection").

Detection is attempted in order of richness, degrading gracefully rather
than failing outright when a data source is unavailable:

    1. ``nvidia-smi`` CLI (no extra Python dependency, present with any
       NVIDIA driver install -- richest data: temperature/power/driver/PCI).
    2. ``pynvml`` bindings, if installed (same data, in-process, useful
       when the worker EXE can't shell out).
    3. ``torch.cuda`` device properties as a last resort (name/VRAM/compute
       capability only -- no temperature/power/driver/PCI id).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

#: Minimum VRAM (GB) a GPU must have to join the farm (goals.md section 3).
MIN_VRAM_GB = 4.0

_NVIDIA_SMI_FIELDS = (
    "index",
    "name",
    "uuid",
    "memory.total",
    "memory.free",
    "memory.used",
    "utilization.gpu",
    "temperature.gpu",
    "power.draw",
    "driver_version",
    "pci.bus_id",
    "compute_cap",
)


@dataclass
class GpuInfo:
    """Snapshot of a single GPU's identity, capability, and live telemetry."""

    index: int
    name: str
    vendor: str = "NVIDIA"
    uuid: Optional[str] = None
    vram_total_mb: Optional[float] = None
    vram_free_mb: Optional[float] = None
    vram_used_mb: Optional[float] = None
    utilization_percent: Optional[float] = None
    temperature_c: Optional[float] = None
    power_watts: Optional[float] = None
    driver_version: Optional[str] = None
    pci_id: Optional[str] = None
    compute_capability: Optional[str] = None
    cuda_version: Optional[str] = None
    cuda_supported: bool = False
    source: str = "unknown"
    """Detection backend that produced this record: nvidia-smi | pynvml | torch."""

    @property
    def vram_total_gb(self) -> Optional[float]:
        """Return total VRAM in GB, when known."""

        return self.vram_total_mb / 1024.0 if self.vram_total_mb is not None else None

    def to_jsonable(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dictionary for the API/dashboard."""

        return {
            "index": self.index,
            "name": self.name,
            "vendor": self.vendor,
            "uuid": self.uuid,
            "vram_total_mb": self.vram_total_mb,
            "vram_free_mb": self.vram_free_mb,
            "vram_used_mb": self.vram_used_mb,
            "vram_total_gb": self.vram_total_gb,
            "utilization_percent": self.utilization_percent,
            "temperature_c": self.temperature_c,
            "power_watts": self.power_watts,
            "driver_version": self.driver_version,
            "pci_id": self.pci_id,
            "compute_capability": self.compute_capability,
            "cuda_version": self.cuda_version,
            "cuda_supported": self.cuda_supported,
            "source": self.source,
        }


@dataclass
class GpuValidationResult:
    """Outcome of validating one GPU against farm join requirements."""

    gpu: GpuInfo
    valid: bool
    reasons: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dictionary."""

        return {"gpu": self.gpu.to_jsonable(), "valid": self.valid, "reasons": self.reasons}


def validate_gpu(gpu: GpuInfo, min_vram_gb: float = MIN_VRAM_GB) -> GpuValidationResult:
    """Validate a single GPU against the farm's minimum join requirements.

    Args:
        gpu: Detected GPU.
        min_vram_gb: Minimum required VRAM in GB.

    Returns:
        Validation result with human-readable reasons for any failure.
    """

    reasons: list[str] = []
    if gpu.vendor.upper() != "NVIDIA":
        reasons.append(f"Unsupported vendor '{gpu.vendor}': only NVIDIA GPUs are supported.")
    if not gpu.cuda_supported:
        reasons.append("CUDA is not supported or could not be detected for this GPU.")
    if gpu.vram_total_gb is None:
        reasons.append("Could not determine VRAM size.")
    elif gpu.vram_total_gb < min_vram_gb:
        reasons.append(f"VRAM {gpu.vram_total_gb:.2f} GB is below the {min_vram_gb:.0f} GB minimum.")
    if gpu.driver_version is None:
        reasons.append("Could not determine driver version (unhealthy/incompatible driver).")
    return GpuValidationResult(gpu=gpu, valid=not reasons, reasons=reasons)


def discover_gpus() -> list[GpuInfo]:
    """Detect all GPUs on this machine, using the richest available source.

    Returns:
        Detected GPUs. Empty list when no GPU or detection method is
        available -- callers should treat that as "no GPUs to validate",
        not as an error.
    """

    gpus = _discover_via_nvidia_smi()
    if gpus:
        return gpus
    gpus = _discover_via_pynvml()
    if gpus:
        return gpus
    return _discover_via_torch()


def discover_and_validate(min_vram_gb: float = MIN_VRAM_GB) -> list[GpuValidationResult]:
    """Detect and validate every GPU on this machine.

    Args:
        min_vram_gb: Minimum required VRAM in GB.

    Returns:
        One validation result per detected GPU.
    """

    return [validate_gpu(gpu, min_vram_gb) for gpu in discover_gpus()]


def _discover_via_nvidia_smi() -> list[GpuInfo]:
    """Detect GPUs by shelling out to `nvidia-smi --query-gpu`.

    Returns:
        Detected GPUs, or an empty list if `nvidia-smi` is unavailable or
        fails (missing/unhealthy driver -- degrade, don't raise).
    """

    if shutil.which("nvidia-smi") is None:
        return []
    query = ",".join(_NVIDIA_SMI_FIELDS)
    try:
        completed = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    gpus: list[GpuInfo] = []
    for line in completed.stdout.strip().splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) != len(_NVIDIA_SMI_FIELDS):
            continue
        values = dict(zip(_NVIDIA_SMI_FIELDS, fields))
        gpus.append(
            GpuInfo(
                index=_int_or(values["index"], default=len(gpus)),
                name=values["name"],
                vendor="NVIDIA",
                uuid=_none_if_na(values["uuid"]),
                vram_total_mb=_float_or_none(values["memory.total"]),
                vram_free_mb=_float_or_none(values["memory.free"]),
                vram_used_mb=_float_or_none(values["memory.used"]),
                utilization_percent=_float_or_none(values["utilization.gpu"]),
                temperature_c=_float_or_none(values["temperature.gpu"]),
                power_watts=_float_or_none(values["power.draw"]),
                driver_version=_none_if_na(values["driver_version"]),
                pci_id=_none_if_na(values["pci.bus_id"]),
                compute_capability=_none_if_na(values["compute_cap"]),
                cuda_version=_cuda_runtime_version(),
                cuda_supported=True,
                source="nvidia-smi",
            )
        )
    return gpus


def _discover_via_pynvml() -> list[GpuInfo]:
    """Detect GPUs via the `pynvml` bindings, when installed.

    Returns:
        Detected GPUs, or an empty list if `pynvml` is not installed or
        NVML initialization fails.
    """

    try:
        import pynvml
    except ImportError:
        return []
    try:
        pynvml.nvmlInit()
    except Exception:
        return []
    try:
        gpus: list[GpuInfo] = []
        driver_version = _pynvml_str(pynvml.nvmlSystemGetDriverVersion())
        for index in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
            try:
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
            except Exception:
                utilization = None
            try:
                temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                temperature = None
            try:
                power_watts = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            except Exception:
                power_watts = None
            try:
                major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                compute_capability = f"{major}.{minor}"
            except Exception:
                compute_capability = None
            try:
                pci_id = _pynvml_str(pynvml.nvmlDeviceGetPciInfo(handle).busId)
            except Exception:
                pci_id = None
            gpus.append(
                GpuInfo(
                    index=index,
                    name=_pynvml_str(pynvml.nvmlDeviceGetName(handle)),
                    vendor="NVIDIA",
                    vram_total_mb=memory.total / (1024**2),
                    vram_free_mb=memory.free / (1024**2),
                    vram_used_mb=memory.used / (1024**2),
                    utilization_percent=float(utilization) if utilization is not None else None,
                    temperature_c=float(temperature) if temperature is not None else None,
                    power_watts=power_watts,
                    driver_version=driver_version,
                    pci_id=pci_id,
                    compute_capability=compute_capability,
                    cuda_version=_cuda_runtime_version(),
                    cuda_supported=True,
                    source="pynvml",
                )
            )
        return gpus
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def _discover_via_torch() -> list[GpuInfo]:
    """Detect GPUs via `torch.cuda` as a last resort.

    Returns:
        Detected GPUs with only name/VRAM/compute-capability known -- no
        temperature, power, driver version, or PCI id, and an empty list
        when torch is unavailable or reports no CUDA device.
    """

    try:
        import torch
    except ImportError:
        return []
    if not torch.cuda.is_available():
        return []
    gpus: list[GpuInfo] = []
    for index in range(torch.cuda.device_count()):
        properties = torch.cuda.get_device_properties(index)
        gpus.append(
            GpuInfo(
                index=index,
                name=properties.name,
                vendor="NVIDIA",
                vram_total_mb=properties.total_memory / (1024**2),
                compute_capability=f"{properties.major}.{properties.minor}",
                cuda_version=torch.version.cuda,
                cuda_supported=True,
                source="torch",
            )
        )
    return gpus


def _cuda_runtime_version() -> Optional[str]:
    """Return the CUDA runtime version reported by torch, when importable.

    Returns:
        CUDA version string, or None if torch/CUDA is unavailable.
    """

    try:
        import torch
    except ImportError:
        return None
    return torch.version.cuda if torch.cuda.is_available() else None


def _pynvml_str(value: Any) -> str:
    """Normalize a pynvml string result across binding versions (str/bytes)."""

    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _none_if_na(value: str) -> Optional[str]:
    """Return None for nvidia-smi's "[Not Supported]"/"N/A" placeholders."""

    stripped = value.strip()
    if not stripped or stripped.upper() in {"N/A", "[NOT SUPPORTED]", "[N/A]"}:
        return None
    return stripped


def _float_or_none(value: str) -> Optional[float]:
    """Convert an nvidia-smi CSV field to float, tolerating placeholders."""

    normalized = _none_if_na(value)
    if normalized is None:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _int_or(value: str, default: int) -> int:
    """Convert an nvidia-smi CSV field to int, falling back to a default."""

    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default
