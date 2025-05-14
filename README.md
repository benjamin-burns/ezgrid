![EZ-Grid logo](logo.png)

# EZ-Grid
*Grid search utility for SLURM workflows*

-------

EZ-Grid aims to simplify and speed up the grid search process by streamlining grid search initialization, execution, and analysis in a highly configurable manner. Essentially a high-level wrapper for the SLURM `sbatch` command in `--array` mode, EZ-Grid abstracts away the need for writing deep, nested for loops over hyperparameters and manually partitioning tasks between jobs. The key features of EZ-Grid are listed below.

* Automatically create and execute `sbatch` scripts for hyperparameter tuning grids all from a simple JSON configuration file
* Reduce mistakes by completing an optional confirmation process to review grid search details before execution
* Change the number of hyperparameter configurations to be run per SLURM array task with a single click—say goodbye to manual task distribution and job runtime calculations
* Produce randomized, memorable, (and sometimes funny!) "petname" identifiers for each hyperparameter configuration (e.g. `openly-vocal-minnow`), along with a codebook to programmatically retrieve configuration details from identifiers
* Easily specify conditional relationships between hyperparameters (e.g., tune `numAttnHeads` only when `encoderType="Transformer"`)
* Seamlessly integrate setup and wrapup scripts to automatically execute before and after the grid search [COMING SOON]
* Track grid search progress through a centralized log [COMING SOON]

## Getting Started

UNDER CONSTRUCTION

## Run EZ-Grid

```
Usage: ezgrid <jsonFilePath> [options]

Positional Arguments:
  jsonFilePath              Path to EZ-Grid configuration file

Optional Arguments:
  -o, --overwrite           Enable save overwrite
  -s, --skip                Skip confirmation step
```

## EZ-Grid Configuration

This section describes the structure and options available in the EZ-Grid JSON configuration file. Example configuration files demonstrating EZ-Grid's functionality are provided in `ExampleConfigs`.

### `gridSearchName` (string)
Name identifier for the grid search run.

### `saveDir` (string)
Grid search output saved at `saveDir/gridSearchName`. Execution fails if the directory already exists, unless save overwrite option `-o` is enabled.

### `script` (string)
Path to the Python script to execute for each hyperparameter combination.

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
Maximum number of SLURM array tasks to run concurrently. _Take care in ensuring that you do not consume large amounts of resources on shared systems for an extended period of time._

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
If true, the unique hyperparameter configuration identifier "petname" will be passed to your script as a command-line argument under the keyword `ezgrid_id`. Suggested for use in program logic for naming consistency.

### `conditional` (object)
Defines conditional hyperparameters—hyperparameters that are only relevant where certain other hyperparameters take on specific values.

Structure:

```json
"conditional": {
    "<conditioned_on>": {
        "<condition_value>": {
            "<conditional_param>": [<levels>]
        }
    }
}
```

Conditional hyperparameters need not be specified, and the field should be omitted entirely if not used. As with the global (unconditional) hyperparameter field, the conditional hyperparameter field can be used to specify conditional, constant inputs by only providing one level.

### `setup` (object)
Specify a script to be executed immediately before the hyperparameter tuning grid starts. Example uses include loading modules, activating execution environments, or preprocessing data. Omit if not used.

Example:

```json
"setup": {
    "path": "path/to/setup.sh",
    "execution": "source"
}
```

In the above example, `source path/to/setup.sh` will run and finish before the grid search begins

### `wrapup` (string)
Path to sbatch script to be executed immediately after the hyperparameter tuning grid ends successfully. EZ-Grid will automatically add the job execution dependency, but the user should supply all other SLURM arguments in the header (including output and error redirection). Example uses include automatically generating grid search summaries, saving results to permenant storage, or running the best model on test data. Omit if not used.

## Planned Updates

* Ability to quickly run/rerun specific hyperparameter configurations (if, for example, some did not successfully complete due to job timeout)