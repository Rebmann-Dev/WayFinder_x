# WayFinder

WayFinder is a local travel planning assistant that pairs a Streamlit chat UI
with a locally-hosted Qwen model, a live flight search backend, and an
ML-driven city safety scorer. Pick a destination on the map (or just type
"flights to Vancouver"), give it a date, and the agent searches flights
across nearby airports and reports a safety read on each destination city.

## Features

- **Chat-driven destination & date updates** — say "flights to Tokyo" or
  "I want to fly next Friday" and the sidebar travel context updates in
  place, no need to touch the date picker or map.
- **Multi-airport flight search** — one query fans out across all airports
  serving the destination metro and renders results grouped by airport with
  airline, duration, stops, and price.
- **Per-destination safety dial** — each airport card shows a compact
  numbered gauge (0–100) with risk band (low / moderate / elevated / high),
  pulled from a KNN-based city safety model.
- **Deterministic safety path** — asking "Is Paris safe?" or "Safety
  Vancouver" skips the model entirely and calls the safety assessment tool
  directly, so results are consistent regardless of phrasing or
  capitalization.
- **Robust location resolution** — multi-word and qualified queries like
  "Vancouver, BC" or "vancouver canada" fall through progressively shorter
  prefixes until the geocoder and airport search both find a match.
- **Token-aware context trimming** — the LLM thread is pre-trimmed to fit
  the model's input budget, dropping oldest tool results first so long
  conversations stay responsive.

## Safety Score Model

WayFinder ships with a custom ML-based safety scoring model that predicts
a continuous safety score for any city or geographic point. The score is
surfaced both as a standalone safety assessment and as the per-airport
dial shown on flight results.

### How it works

The core is a feedforward Multilayer Perceptron (MLP) regression model
implemented in PyTorch. The production architecture uses three fully
connected hidden layers (128 → 64 → 32) with ReLU activations, dropout,
and L2 weight decay to keep the model honest against a relatively small
~500-row labeled city dataset. It's trained with MSE loss and Adam on an
80/20 hold-out split, with early stopping based on validation RMSE.

At inference, WayFinder actually runs two independently trained
variants in parallel — a crime-aware model (uses city-level crime and
safety indices where available) and a crime-agnostic model (geographic
and macro features only). Comparing the two acts as a built-in
cross-check and gracefully degrades when a queried point falls outside
the labeled city catalog.

### Features

The feature vector for a given location combines several broad groups:

- **City-level crime and safety indices** — Numbeo-style crime and
  perceived-safety scores for labeled cities. The target city's own
  crime index is strictly excluded during training to prevent target
  leakage.
- **KNN neighborhood aggregates** — crime and safety averages computed
  over the nearest labeled cities (weighted and unweighted k=5 / k=10),
  plus distance-to-nearest-labeled-city features. This is what lets the
  model score unseen locations by interpolating from labeled neighbors.
- **Density & gravity features** — log-transformed population counts,
  population gravity, and city counts within 50 / 100 / 250 km radii.
- **Country-level macro indicators** — GDP, GDP per capita,
  unemployment, homicide rate, life expectancy, and governance signals
  (rule of law, political stability, press freedom, Global Peace Index).
- **Geographic base features** — latitude, longitude, and administrative
  country identifiers.

Data is sourced from open global datasets including the World Bank
(socioeconomic and homicide data), UNODC Global Study on Homicide, the
Global Peace Index, and Reporters Without Borders' World Press Freedom
Index.

### Handling unseen cities

Most real-world queries don't land on a perfectly labeled city. For any
point on Earth, the feature pipeline geocodes the query, finds the
nearest labeled cities via KNN, and computes neighborhood aggregates
plus macro context for the surrounding region. If city-level crime data
is available for the queried point the crime-aware model runs at full
fidelity; otherwise the score falls back to the crime-agnostic regime,
and the returned payload flags the confidence accordingly.

### Outputs

Each safety assessment returns:

- **`safety_score`** — a continuous 0–100 value (higher is safer).
- **`risk_band`** — a bucketed label derived from the score:
  - `low` (75+)
  - `moderate` (55–74)
  - `elevated` (35–54)
  - `high` (<35)
- **Factor breakdown** — the most influential city-specific signals
  behind the score, including neighborhood crime / safety averages and
  the nearest labeled city's own values, used to explain the result
  conversationally in chat.
- **Confidence indicator** — whether the crime-aware model ran with
  full feature availability or fell back to the crime-agnostic regime.

In the chat UI these outputs are rendered as a conversational markdown
response for standalone safety queries, and as a compact numbered dial
(`0 ├──┼──┼──┼──┤ 100` with a pointer and risk band label) on each
airport's flight card.

# Installation

### Prerequisites: 

#### Python Version
For this project we are using Python version 3.12.8, conda automatically will install and set the correct python version for the project so there is nothing that needs to be done.

#### 1. Install Miniconda

If you are already using Anaconda or any other conda distribution, feel free to skip this step.

Miniconda is a minimal installer for `conda`, which we will use for managing environments and dependencies in this project. Follow these steps to install Miniconda or go [here](https://docs.anaconda.com/miniconda/install/) to reference the documentation: 

1. Open your terminal and run the following commands:
```bash
   $ mkdir -p ~/miniconda3

   <!-- If using Apple Silicon chip M1/M2/M3 -->
   $ curl https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh -o ~/miniconda3/miniconda.sh
   <!-- If using intel chip -->
   $ curl https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh -o ~/miniconda3/miniconda.sh

   $ bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
   $ rm ~/miniconda3/miniconda.sh
```

2. After installing and removing the installer, refresh your terminal by either closing and reopening or running the following command.
```bash
$ source ~/miniconda3/bin/activate
```

3. Initialize conda on all available shells.
```bash
$ conda init --all
```

You know conda is installed and working if you see (base) in your terminal. Next, we want to actually use the correct environments and packages.

#### 2. Install Make

Make is a build automation tool that executes commands defined in a Makefile to streamline tasks like compiling code, setting up environments, and running scripts. [more information here](https://formulae.brew.sh/formula/make)

##### Installation

`make` is often pre-installed on Unix-based systems (macOS and Linux). To check if it's installed, open a terminal and type:
```bash
make -v
```

If it is not installed, simply use brew:
```bash
$ brew install make
```

#### 3. Install Docker

Docker is a containerization platform that packages your application, models, and dependencies into a consistent runtime environment, ensuring your multi-agent system and flight APIs run reliably across development, testing, and deployment without environment-related failures.

1. Download Docker Desktop from the official site:  
   https://docs.docker.com/get-docker/

2. Follow the installation instructions for your operating system (Mac, Windows, or Linux).

3. After installation, verify Docker is running:
```bash
  docker --version
```


### Step-by-step Installation
```bash
# Clone the repository
git clone <your-repo-url>
cd wayfinder

# Create virtual environment (recommended)
make create
```

## Quick Setup

1. **Install dependencies:**
```bash
  $ make create
        or
  $ make update
```

2. **Setup API Docker Container**
```bash
  $ make docker-compose-up
```

3. **Run the streamlit server**
```bash
  $ make run
```

#### Available Commands

The following commands are available in this project’s `Makefile`:

- **Set up the environment**:

    This will create the environment from the environment.yml file in the root directory of the project.

    ```bash
      $ make create
    ```

- **Update the environment**:

    This will update the environment from the environment.yml file in the root directory of the project. Useful if pulling in new changes that have updated the environment.yml file.

    ```bash
      $ make update
    ```

- **Remove the environment**:

    This will remove the environment from your shell. You will need to recreate and reinstall the environment with the setup command above.

    ```bash
    $ make clean
    ```

- **Activate the environment**:

    This will activate the environment in your shell. Keep in mind that make will not be able to actually activate the environment, this command will just tell you what conda command you need to run in order to start the environment.

    Please make sure to activate the environment before you start any development, we want to ensure that all packages that we use are the same for each of us.

    ```bash
    $ make activate
    ```

    Command you actually need to run in your terminal:
    ```bash
    $ conda activate wayfinder
    ```

- **Deactivate the environment**:

    This will Deactivate the environment in your shell.

    ```bash
    $ make deactivate
    ```

- **Quick start**:

    This command will run the quick_start python script to generate the dataset

    ```bash
    $ make quick
    ```

- **run jupyter notebook**:

    This command will run jupyter notebook from within the conda environment. This is important so that we can make sure the package versions are the same for all of us! Please make sure that you have activated your environment before you run the notebook.

    ```bash
    $ make notebook
    ```

- **Export packages to env file**:

    This command will export any packages you install with either `conda install ` or `pip install` to the environment.yml file. This is important because if you add any packages we want to make sure that everyones machine knows to install it.

    ```bash
    $ make freeze
    ```

- **Verify conda environment**:

    This command will list all of your conda envs, the environment with the asterick next to it is the currently activated one. Ensure it is correct.

    ```bash
    $ make verify
    ```

#### Example workflows:

To simplify knowing which commands you need to run and when you can follow these instructions:

- **First time running, no env installed**:

    In the scenario where you just cloned this repo, or this is your first time using conda. These are the commands you will run to set up your environment.

    ```bash
    <!-- Make sure that conda is initialized -->
    $ conda init --all

    <!-- Next create the env from the env file in the root directory. -->
    $ make create

    <!-- After the environment was successfully created, activate the environment. -->
    $ conda activate wayfinder

    <!-- verify the conda environment -->
    $ make verify

    <!-- verify the python version you are using. This should automatically be updated to the correct version 3.12.2 when you enter the environment. -->
    $ python --version

    <!-- Run jupyter notebook and have some fun! -->
    $ make notebook
    ```

- **Installing a new package**:

    While we are developing, we are going to need to install certain packages that we can utilize. Here is a sample workflow for installing packages. The first thing we do is verify the conda environment we are in to ensure that only the required packages get saved to the environment. We do not want to save all of the python packages that are saved onto our system to the `environment.yml` file. 

    Another thing to note is that if the package is not found in the conda distribution of packages you will get a `PackagesNotFoundError`. This is okay, just use pip instead of conda to install that specific package. Conda thankfully adds them to the environment properly.

    ```bash
    <!-- verify the conda environment -->
    $ make verify

    <!-- Install the package using conda -->
    $ conda install <package_name>

    <!-- If the package is not found in the conda channels, install the package with pip. -->
    $ pip install <package_name>

    <!-- If removing a package. -->
    $ conda remove <package_name>
    $ pip remove <package_name>

    <!-- Export the package names and versions that you downloaded to the environment.yml file -->
    make freeze
    ```

- **Daily commands to run before starting development**:

    Here is a sample workflow for the commands to run before starting development on any given day. We want to first pull all the changes from github into our local repository, 

    ```brew
    <!-- Pull changes from git -->
    $ git pull origin main

    <!-- Update env based off of the env file. It is best to deactivate the conda env before you do this step-->
    $ conda deactivate
    $ make update
    $ conda activate wayfinder

    $ make notebook
    ```

- **Daily commands to run after finishing development**:

    Here is a sample workflow for the commands to run after finishing development for any given day.

    ```brew
    $ conda deactivate

    <!-- If you updated any of the existing packages, freeze to the environment.yml file. -->
    $ make freeze

    <!-- Commit changes to git -->
    $ git add .
    $ git commit -m "This is my commit message!"
    $ git push origin <branch_name>
    ```


## Contributors
<table>
  <tr>
    <td>
        <a href="https://github.com/IanRebmann.png">
          <img src="https://github.com/IanRebmann.png" width="100" height="100" alt="Ian Rebmann"/><br />
          <sub><b>Ian Rebmann</b></sub>
        </a>
      </td>
     <td>
      <a href="https://github.com/omarsagoo.png">
        <img src="https://github.com/omarsagoo.png" width="100" height="100" alt="Omar Sagoo"/><br />
        <sub><b>Omar Sagoo</b></sub>
      </a>
    </td>
    <td>
      <a href="https://github.com/Ajmaljalal.png">
        <img src="https://github.com/Ajmaljalal.png" width="100" height="100" alt="Ajmal Jalal"/><br />
        <sub><b>Ajmal Jalal</b></sub>
      </a>
    </td>
  </tr>
</table>