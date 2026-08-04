Here is the updated combined prompt with the local/cloud split, EXE distribution, licensing rules, and distribution details included:

# LLM-IDE GPU Farm Manager – Project Description

## Overview

Build a distributed GPU Farm Manager for **LLM-IDE** (`https://github.com/drunkenbot-ai/LLM-IDE`).

The **LLM-IDE training engine/core already exists**. This project is not about building a new trainer or an inference system. It is about building the infrastructure around the existing training engine so it can run on multiple machines as a managed GPU farm.

The system must support **training only**.

The platform should have **two separate workflows**:

1. **Local GPU Farm**
   For private/local machines. No license or subscription check is required.

2. **Cloud GPU Farm**
   For shared or remote cloud GPUs. Access to cloud GPU pool must be controlled by **subscription-based GPU hours** and a **valid license**. Licensing is already handled by `https://github.com/drunkenbot-ai/cloud-service`.

The initial goal is to create a reliable **small-scale private GPU farm**, with the architecture designed so it can later expand to a public GPU marketplace if needed.

---

# Objectives

* Distribute LLM training workloads across multiple machines.
* Provide centralized monitoring and management.
* Automatically schedule training jobs.
* Efficiently distribute project files to worker machines.
* Monitor hardware health and utilization.
* Support local GPUs and cloud GPUs through separate workflows.
* Make adding new worker machines simple.
* Scale from a few local PCs to hundreds of workers later.

---

# Core Components

## 1. Farm Manager (Web Application)

Develop a modern web application that acts as the central controller for the GPU farm.

Responsibilities:

* Manage all connected worker machines.
* Manage the local machine as a worker too.
* View every GPU across the farm.
* Support both **local farm mode** and **cloud farm mode**.
* Real-time monitoring using WebSockets.
* Manage training jobs.
* Manage resource pools.
* Display live statistics.
* Configure scheduling.
* View worker health.
* Centralized logging.

Dashboard should display:

* Connected workers
* Worker status (Online, Offline, Busy, Idle)
* GPU utilization
* VRAM usage
* CPU utilization
* RAM usage
* Disk usage
* Network usage
* GPU temperature, if available
* Running jobs
* Queued jobs
* Failed jobs
* Completed jobs
* Local pool status
* Cloud pool status
* License/subscription status for cloud usage

Farm statistics:

* Total workers
* Total GPUs
* Available GPUs
* Busy GPUs
* Total VRAM
* Farm utilization
* Running training jobs
* Average load
* Worker health
* GPU-hours consumed
* GPU-hours remaining for subscribed cloud users

Job controls:

* Submit training
* Start
* Pause
* Resume
* Stop
* Cancel
* Restart
* View logs
* Download outputs

---

## 2. Python Worker Client

Develop a lightweight **Python worker client** that is installed on every worker machine.

Important: the client must be distributed as a **Windows EXE**, not as raw Python scripts.

Responsibilities:

* Run in the background.
* Provide a Windows system tray/taskbar application.
* Auto-start with Windows.
* Connect to Farm Manager.
* Authenticate.
* Maintain heartbeat.
* Wait for new training jobs.
* Download project files.
* Execute LLM-IDE training.
* Upload logs and outputs.
* Continuously report resource usage.
* Recover after reboot or temporary disconnect.

Supported operations:

* Start
* Pause
* Resume
* Stop
* Cancel

The EXE should include all runtime dependencies needed by the user so they do not need to install Python manually.

---

## 3. GPU Discovery & Validation

Automatically detect all GPUs installed on the machine.

Collect:

* GPU name
* Vendor
* VRAM
* CUDA support
* CUDA version
* Compute capability
* Driver version
* PCI ID
* Utilization
* Temperature
* Power usage, if available

Validate before joining the farm.

Minimum requirements:

* NVIDIA GPU
* CUDA supported
* Minimum 4 GB VRAM
* Healthy CUDA runtime
* Compatible driver

Only validated GPUs can participate in the farm.

---

## 4. GPU Selection

Machines may have multiple GPUs.

The client should allow the user to choose:

* Individual GPUs
* Multiple GPUs
* All supported GPUs

Only selected GPUs become part of the farm.

Selections must persist across restarts.

---

## 5. Training Job Distribution

The system distributes **LLM-IDE training projects**.

When a worker receives a job it should:

1. Download project files from the manager or file service.
2. Verify integrity.
3. Cache the project locally.
4. Download only changed files on future runs.
5. Prepare the training environment.
6. Launch the existing LLM-IDE training engine.
7. Stream logs and progress.
8. Upload outputs and checkpoints.
9. Report completion status.

The system should support resumable downloads and future delta synchronization.

---

## 6. Scheduler

Implement a scheduler dedicated to training workloads.

Scheduling should consider:

* Available GPUs
* Free VRAM
* GPU utilization
* CPU utilization
* RAM availability
* Disk space
* Worker availability
* Resource pool selection
* Local mode vs cloud mode
* Subscription/license validity for cloud usage

Prevent resource over-allocation.

Support future multi-GPU training jobs.

---

## 7. Resource Pools

Implement **Resource Pools** to organize GPUs logically.

A Resource Pool is a collection of GPUs selected manually or dynamically.

Pools may be created using:

* CUDA version
* CUDA major version
* GPU vendor
* GPU model
* GPU series
* Compute capability
* VRAM size
* Driver version
* Machine
* Labels
* Tags
* Assigned project
* Manual selection

Examples:

* RTX 4090 Pool
* RTX 30 Series
* CUDA 12 Pool
* CUDA 12.8 Pool
* 24 GB VRAM Pool
* Fine-Tuning Pool
* Experimental Pool
* Project Alpha Pool
* Development Pool

A GPU may belong to multiple pools simultaneously.

Projects should target Resource Pools rather than specific GPUs.

Pool management:

* Create
* Edit
* Rename
* Delete
* Manual membership
* Rule-based membership
* Enable/disable
* Reserve for projects
* View utilization
* View health

Each pool should display:

* Number of GPUs
* Available GPUs
* Busy GPUs
* Total VRAM
* Utilization
* Assigned projects

---

## 8. Tagging System

Every worker and GPU should support metadata tags.

Example GPU tags:

* nvidia
* rtx4090
* cuda12
* cuda12.8
* 24gb
* workstation
* office
* training
* experimental
* project-alpha

These tags should be usable for:

* Resource Pools
* Scheduling
* Filtering
* Searching
* Future automation

---

## 9. Local GPU Farm Workflow

This workflow is for private/local use.

Requirements:

* No license validation is required.
* No subscription check is required.
* Local machines can be added directly to the farm.
* Local pool can be used immediately for training.
* The Farm Manager should manage local GPUs exactly as part of the private farm.
* Local jobs should run without contacting the licensing service.

This workflow is intended for private training environments.

---

## 10. Cloud GPU Farm Workflow

This workflow is for cloud/remote GPU usage.

Requirements:

* Access must require a valid license.
* Access must require active GPU-hours subscription.
* Licensing is already handled by `drunkenbot-ai/cloud-service`.
* The Farm Manager must verify entitlement before enabling cloud pool usage.
* If license or subscription is invalid, the user must not be allowed to use cloud GPUs.
* Cloud GPU access should be separated from local farm access.

Cloud workflow should include:

* License validation
* Subscription state check
* GPU-hours accounting
* Usage limits
* Expiration handling
* Cloud pool access control

---

## 11. Monitoring

Collect real-time telemetry:

GPU:

* Utilization
* VRAM
* Temperature
* Fan speed, if available
* Power usage
* Clock speeds

CPU:

* Usage
* Temperature

Memory:

* RAM usage
* Swap usage

Storage:

* Disk usage
* Read/write throughput

Network:

* Upload/download
* Latency

Workers should continuously stream telemetry to the Farm Manager.

Historical graphs should be available.

---

## 12. File and Project Distribution

The farm must distribute complete training projects to worker machines.

The system should support:

* Project packaging
* File syncing
* Integrity verification
* Local caching on workers
* Delta updates for changed files
* Checkpoints and output upload
* Resume from partial downloads where possible

Workers should not depend on manual file copying.

---

## 13. Packaging and Distribution

The worker client must be packaged as a **native Windows executable**.

Requirements:

* Distribute as EXE from the website
* No Python installation required on the user machine
* No raw `.py` script distribution to end users
* Bundled dependencies
* Auto-start capable
* System tray UI included
* Upgrade/update path should be considered

---

## 14. Architecture

Design a modular client-server architecture.

Components:

* Farm Manager Backend API
* Web Dashboard
* Scheduler Service
* Worker Client EXE
* File Distribution Service
* Monitoring Service
* Database
* Shared Python SDK
* Licensing/entitlement integration for cloud workflow

The Shared SDK should contain:

* API client
* Authentication
* Common models
* Job protocol
* Resource protocol
* Serialization
* Utilities

The architecture should keep local and cloud workflows separated while sharing common infrastructure where possible.

---

## 15. Future Expansion

Although not part of the initial implementation, the architecture should accommodate future features such as:

* Public GPU sharing
* GPU rentals
* User accounts
* Authentication and authorization
* Billing
* Remote Internet workers
* Docker-based execution
* Multi-tenant isolation
* Resource quotas
* Priority scheduling
* Reservations
* REST API
* Plugin system

These capabilities should not require major architectural redesign.

---

# Goal

Create a production-quality distributed GPU Farm Manager that transforms multiple Windows machines running **LLM-IDE** into a unified training cluster.

The platform should provide centralized monitoring, intelligent scheduling, project synchronization, resource pooling, GPU selection, telemetry, and reliable execution of distributed LLM training workloads.

It must support two distinct workflows:

* **Local GPU Farm** for private training without licensing
* **Cloud GPU Farm** for subscription-based GPU-hour access with license validation

The system should remain scalable and extensible for future expansion.
