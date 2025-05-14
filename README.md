![EZ-Grid logo](logo.png)

# EZ-Grid
*Grid search utility for SLURM workflows*

-------

EZ-Grid aims to simplify and speed up the grid search process by streamlining grid search initialization, execution, and analysis in a highly configurable manner. Essentially a high-level wrapper for the SLURM `sbatch` command in `--array` mode, EZ-Grid removes the need for writing deep, nested for loops and manually partitioning tasks between jobs. The key features of EZ-Grid are listed below.

* Automatically create and execute `sbatch` scripts for hyperparameter tuning grids all from a simple JSON configuration file
* Reduce mistakes by completing an optional confirmation process to review grid search details before execution
* Change the number of hyperparameter configurations to be run per job array task with a single click - no more manual task distribution or job runtime calculations
* Produce randomized, memorable, (and sometimes funny!) "petname" identifiers for each hyperparameter configuration (e.g. `barely-happy-rabbit`), along with a codebook to programmatically retrieve configuration details from identifiers
* Easily specify conditional relationships between hyperparameters (e.g., tune `numAttnHeads` only when `encoderType="Transformer"`) [COMING SOON]
* Seamlessly integrate setup and wrapup scripts to automatically execute before and after the grid search [COMING SOON]
* Track grid search progress through a centralized log [COMING SOON]

## Getting Started

TEXT

## Run EZ-Grid

Configure JSON file

```
Usage: ezgrid <jsonFilePath> [options]

Positional Arguments:
  jsonFilePath              Path to EZ-Grid configuration file

Optional Arguments:
  -o, --overwrite           Enable save overwrite
  -s, --skip                Skip confirmation step
```

## EZ-Grid JSON Configuration

This section describes the structure and options available in the EZ-Grid JSON configuration file. Example configuration files demonstrating EZ-Grid's functionality are provided in `ExampleConfigs`.

### `gridSearchName` (string)
Name identifier for the grid search run.

### `saveDir` (string)
Grid search output saved at `saveDir/gridSearchName`. Execution fails if the directory already exists, unless save overwrite option `-o` is enabled.

### `script` (string)
Path to the python script to execute for each hyperparameter combination.

### `hyperparameters` (object)
Dictionary of hyperparameters to sweep. Each key is the hyperparameter name, and the value is a list hyperparameter levels. Hyperparameter values will be passed as _keyword command-line arguments_ to `script`. Non-hyperparameter script arguments can also be included here as lists with one element.

Example:
```json
"hyperparameters": {
  "optimizer": ["adam", "sgd"],
  "batch_size": [32, 64],
  "learning_rate": [0.001, 0.01],
  "epochs": [10, 20],
  "inputDir": ["/path/to/data"]
}
```

### `timePerConfig` (string)
Maximum time for a single run of `script` in format `"d-hh:mm:ss"`. This field replaces the need for specifying `--time` in the SLURM sbatch header, as EZ-Grid automatically fills this field based `timePerConfig` and `configsPerJob`.

### `configsPerJob` (integer)
Number of distinct hyperparameter configurations to run within a single job array task. That is, `"configsPerJob": 1` submits a separate task for each configuration.

### `maxSimultaneousJobs` (integer)
Maximum number of SLURM array tasks to run in parallel.

### `slurm` (object)
SLURM sbatch job configuration header. Refer to SLURM documentation for field details. Omit the `--time` field and use `timePerConfig` instead.

Example:

```json
"slurm": {
  "nodes": "1",
  "ntasks": "1",
  "gpus-per-node": "0",
  "cpus-per-task": "4",
  "mem": "80GB",
  "account": "myAccount",
  "partition": "myPartition"
}
```

### `passConfigIdToScript` (boolean)
If true, a unique hyperparameter configuration identifier "petname" will be passed to your script as a command-line argument under the keyword `ezgrid_id`.
