# WayFinder

An AI-powered travel planning assistant that combines a local large language model with real-time flight search and ML-based destination safety scoring. Users can search flights through natural language conversation, explore destinations on an interactive map, and get safety assessments powered by an ensemble of neural network and random forest models.

## Features

- **Conversational flight search** — Ask for flights in plain English. The agent resolves city names to airport codes, validates dates, and returns real results from a flight API. Strict guardrails prevent the LLM from hallucinating flight data.
- **Multi-airport flight search** — One query fans out across all airports serving the destination metro and renders results grouped by airport with airline, duration, stops, and price.
- **Safety scoring** — Select any location on an interactive map and get a safety score (0-100) with a risk band (low / moderate / elevated / high). Predictions are made by an ensemble of a PyTorch MLP and a scikit-learn Random Forest trained on 45 features including KNN neighborhood crime/safety indices, population density, and country-level macro indicators.
- **Per-destination safety dial** — Each airport card shows a compact numbered gauge (0-100) with risk band, pulled from a KNN-based city safety model.
- **Deterministic safety path** — Asking "Is Paris safe?" or "Safety Vancouver" calls the safety assessment tool directly, so results are consistent regardless of phrasing or capitalization.
- **Robust location resolution** — Multi-word and qualified queries like "Vancouver, BC" or "vancouver canada" fall through progressively shorter prefixes until the geocoder and airport search both find a match.
- **Local LLM** — Runs Qwen 2.5 1.5B Instruct locally with tool-calling support. No API keys or cloud dependencies for the language model. Supports CUDA, Apple Silicon (MPS), and CPU.
- **Interactive map** — Leaflet.js-based location picker built as a custom Streamlit component for selecting destinations and triggering safety assessments.
- **Token-aware context trimming** — The LLM thread is pre-trimmed to fit the model's input budget, dropping oldest tool results first so long conversations stay responsive.

## Safety Score Model

WayFinder ships with a custom ML-based safety scoring model that predicts a continuous safety score for any city or geographic point. The score is surfaced both as a standalone safety assessment and as the per-airport dial shown on flight results.

### How it works

The core is a feedforward Multilayer Perceptron (MLP) regression model implemented in PyTorch. The production architecture uses three fully connected hidden layers (128 -> 64 -> 32) with ReLU activations, dropout, and L2 weight decay to keep the model honest against a relatively small ~500-row labeled city dataset. It's trained with MSE loss and Adam on an 80/20 hold-out split, with early stopping based on validation RMSE.

At inference, WayFinder actually runs two independently trained variants in parallel -- a crime-aware model (uses city-level crime and safety indices where available) and a crime-agnostic model (geographic and macro features only). Comparing the two acts as a built-in cross-check and gracefully degrades when a queried point falls outside the labeled city catalog.

### Model features

The feature vector for a given location combines several broad groups:

- **City-level crime and safety indices** -- Numbeo-style crime and perceived-safety scores for labeled cities. The target city's own crime index is strictly excluded during training to prevent target leakage.
- **KNN neighborhood aggregates** -- Crime and safety averages computed over the nearest labeled cities (weighted and unweighted k=5 / k=10), plus distance-to-nearest-labeled-city features. This is what lets the model score unseen locations by interpolating from labeled neighbors.
- **Density & gravity features** -- Log-transformed population counts, population gravity, and city counts within 50 / 100 / 250 km radii.
- **Country-level macro indicators** -- GDP, GDP per capita, unemployment, homicide rate, life expectancy, and governance signals (rule of law, political stability, press freedom, Global Peace Index).
- **Geographic base features** -- Latitude, longitude, and administrative country identifiers.

Data is sourced from open global datasets including the World Bank (socioeconomic and homicide data), UNODC Global Study on Homicide, the Global Peace Index, and Reporters Without Borders' World Press Freedom Index.

### Handling unseen cities

Most real-world queries don't land on a perfectly labeled city. For any point on Earth, the feature pipeline geocodes the query, finds the nearest labeled cities via KNN, and computes neighborhood aggregates plus macro context for the surrounding region. If city-level crime data is available for the queried point the crime-aware model runs at full fidelity; otherwise the score falls back to the crime-agnostic regime, and the returned payload flags the confidence accordingly.

### Outputs

Each safety assessment returns:

- **`safety_score`** -- A continuous 0-100 value (higher is safer).
- **`risk_band`** -- A bucketed label derived from the score:
  - `low` (75+)
  - `moderate` (55-74)
  - `elevated` (35-54)
  - `high` (<35)
- **Factor breakdown** -- The most influential city-specific signals behind the score, including neighborhood crime / safety averages and the nearest labeled city's own values, used to explain the result conversationally in chat.
- **Confidence indicator** -- Whether the crime-aware model ran with full feature availability or fell back to the crime-agnostic regime.

In the chat UI these outputs are rendered as a conversational markdown response for standalone safety queries, and as a compact numbered dial with a pointer and risk band label on each airport's flight card.

## Tech Stack

| Layer | Technology |
|-------|------------|
| UI | Streamlit, Leaflet.js (custom component) |
| LLM | Qwen 2.5 1.5B Instruct (HuggingFace Transformers) |
| ML Models | PyTorch (MLP), scikit-learn (Random Forest), joblib |
| Data | Pandas, NumPy |
| Flight API | Docker container (scraper service), Requests |
| Environment | Conda (Python 3.12.8) |

## Project Structure

```
WayFinder/
├── app/
│   ├── main.py                                 # Streamlit entry point; bootstraps app UI
│   ├── core/
│   │   └── config.py                           # Global settings: model config, agent_max_steps, feature toggles, flight_scraper_mode
│   │
│   ├── ui/
│   │   ├── chat_page.py                        # Main chat screen: map, safety panel, destination picker, chat layout
│   │   ├── chat_handlers.py                    # Handles user submit flow and streams AgentStreamEvent responses into UI
│   │   ├── renderers.py                        # Renders streaming assistant text, status events, tool results
│   │   ├── styles.py                           # Global Streamlit CSS/theme overrides
│   │   └── translate_widget.py                 # Floating live translation widget
│   │
│   ├── agents/
│   │   ├── local_tool_agent.py                 # Core orchestration engine:
│   │   │                                       # - intent detection
│   │   │                                       # - flight-disabled guard
│   │   │                                       # - flight pre-resolution
│   │   │                                       # - safety short-circuit
│   │   │                                       # - JSON-first country lookup
│   │   │                                       # - bounded LLM + tool loop
│   │   │                                       # - narration / hallucination guards
│   │   │                                       # - final response / fallback handling
│   │   ├── tool_executor.py                    # Executes validated tool calls (search_flights, search_airports, get_safety_assessment, etc.)
│   │   ├── tool_call_parser.py                 # Parses model-emitted <tool_call> blocks into structured calls
│   │   ├── tool_definitions.py                 # OpenAI-style tool schema definitions exposed to the LLM
│   │   └── utils/
│   │       ├── intent.py                       # Intent routing helpers (flight vs safety vs non-flight)
│   │       ├── thread.py                       # Latest-user-message utilities, thread slicing, search-state helpers
│   │       ├── grounding.py                    # Airport/date grounding helpers from tool results + user text
│   │       ├── clarification.py                # Strict airport/date clarification rules before flight execution
│   │       ├── rendering.py                    # Tool-result render helpers for flights and safety responses
│   │       └── ...                             # Additional parsing / extraction helpers used inside LocalToolAgent
│   │
│   ├── tools/
│   │   └── flight_search.py                    # FlightSearchTool facade; delegates to provider selected by get_flight_provider()
│   │
│   ├── services/
│   │   ├── model_service.py                    # Local LLM loading, token counting, stream_agent_turn(), inference loop
│   │   ├── memory_service.py                   # Session-state / conversation memory helpers
│   │   ├── airport_search_service.py           # Airport lookup from local dataset/CSV
│   │   ├── safety_service.py                   # Safety geocoding + model scoring interface
│   │   ├── tavily_service.py                   # Web search fallback plus JSON cache checks for destination knowledge
│   │   ├── knowledge_service.py                # Loads full local country JSON files via load_country()
│   │   └── flight/
│   │       ├── __init__.py                     # Exports get_flight_provider()
│   │       ├── base.py                         # FlightProvider interface / abstract contract
│   │       ├── factory.py                      # Provider selection by settings.flight_scraper_mode
│   │       ├── disabled.py                     # Safe no-op provider; returns disabled-flight response
│   │       ├── stub.py                         # Deterministic mock flight provider for testing/dev
│   │       └── docker_scraper.py               # Live provider wrapping Go scraper API on localhost:8080
│   │
│   ├── prompts/
│   │   ├── system_prompts.py                   # System behavior instructions for travel assistant persona
│   │   └── prompt_builder.py                   # Message formatting / prompt construction for model input
│   │
│   ├── models/
│   │   ├── chat.py                             # ChatMessage dataclass / chat model types
│   │   ├── flight_search.py                    # FlightSearchRequest schema and request validation helpers
│   │   └── safety/
│   │       ├── schemas.py                      # SafetyRequest / SafetyResult models
│   │       ├── predictor.py                    # Ensemble predictor (MLP + RF)
│   │       ├── v6_features.py                  # Feature engineering pipeline
│   │       ├── v6_config.py                    # Model paths / constants
│   │       ├── v6_train.py                     # Training code
│   │       ├── v6_data_loading.py              # Data loading + train/val/test splits
│   │       ├── feature_pipeline.py             # Scaling / column loading / inference pipeline
│   │       └── artifacts/                      # Saved model weights, encoders, scaler
│   │
│   ├── components/
│   │   └── location_picker/                    # Custom Streamlit map/location picker component
│   │
│   └── data/
│       ├── compiled_model_ready/               # City-level safety / demographic / feature-engineering inputs
│       ├── global_data/                        # Country-level macro indicators
│       └── countries/                          # Local country knowledge JSON files used by JSON-first lookup
│
├── notebooks/
│   ├── 01_data_cleaning/                       # Data merging, cleaning, normalization, imputation
│   ├── 02_exploratory_data_analysis/           # Visualizations, distributions, maps
│   ├── 03_model_design_and_training/           # Feature engineering + model training experiments
│   ├── 04_model_optimization/                  # Inference / optimization work
│   └── 05_model_analysis_and_evaluation/       # Metrics, comparisons, error analysis
│
├── Makefile                                    # Dev shortcuts / app run commands
├── environment.yml                             # Conda dependencies
└── docker-compose.yml                          # Local scraper / supporting services
```
### The Key New Layer: pipeline/
This is the biggest improvement. Right now chat_orchestrator.py is just 30 lines of keyword matching . The new pipeline handles everything that happens before the agent sees the query:

#### User Input
    ↓
input_processor.py       ← spell check, typo fix, NER (extracts country/city names)
    ↓                       asks clarification if country is ambiguous or missing
intent_classifier.py     ← classifies: safety / flight / explore / translate / general
    ↓
orchestrator.py          ← routes to: FlightAgent | LocalToolAgent | SafetyService | Tavily
    ↓
response_builder.py      ← assembles answer + sources + confidence + memory write
    ↓
API route OR Streamlit UI


### LLM handeling Diagram

flowchart TD
    A[User message enters chat UI] --> B[LocalToolAgent.run(messages)]
    B --> C[Emit status: Preparing your response]
    C --> D[Intent detection<br/>is_flight_search_intent(messages)<br/>is_safety_intent(messages)]

    D --> E{Flight intent?}
    E -- Yes --> F{settings.flight_scraper_mode == off?}
    F -- Yes --> G[Short-circuit done<br/>Return disabled-flight message]
    F -- No --> H[Flight pre-resolution]

    H --> H1[_update_destination_from_chat(messages)]
    H1 --> H2[_pre_resolve_destination(thread)]
    H2 --> H3[_pre_resolve_origin(thread)]
    H3 --> H4[_pre_inject_date(thread, messages)]
    H4 --> I[thread prepared with airport/date context]

    E -- No --> J{Safety intent?}
    J -- Yes --> K[_run_safety_short_circuit(messages)]
    K --> K1{Location resolved?}
    K1 -- Yes --> K2[ToolExecutor.run get_safety_assessment]
    K2 --> K3[render_safety_result(result)]
    K3 --> K4[Return done]
    K1 -- No --> L[Fall through to model path]

    J -- No --> M{Destination knowledge query?}
    M -- Yes --> N[_check_country_json(latest_q)]
    N --> N1{Mode = specific?}
    N1 -- Yes --> N2[Return formatted JSON answer directly]
    N1 -- No --> N3{Mode = broad or followup?}
    N3 -- Yes --> N4[Set _json_context in session_state]
    N4 --> O[Insert JSON context into thread as system message]
    N3 -- No --> L
    M -- No --> L

    I --> P[Agent loop for step in range(agent_max_steps)]
    O --> P
    L --> P

    P --> Q[Compute loop state<br/>grounded_codes = user_explicit_iata_codes + airport_codes_from_tool_results<br/>explicit_dates = user_explicit_dates<br/>already_searched = searched_since_last_user_message]

    Q --> R{Flight short-circuit eligible?}
    R -- Yes --> S[_run_short_circuit(thread, messages, grounded_codes, explicit_dates, date_str)]
    S --> S1[Iterate ranked_destination_candidates(thread)]
    S1 --> S2[ToolExecutor.run search_flights for each candidate]
    S2 --> S3[_airport_safety_brief(candidate, cache)]
    S3 --> S4[render_multi_airport_results(all_results)]
    S4 --> S5[Return done]
    R -- No --> T[Trim thread<br/>_trim_thread_to_fit(...)]

    T --> U[LLM generation<br/>ModelService.stream_agent_turn(thread, tools=TOOLS)]
    U --> V[Collect full_text]
    V --> W[parse_tool_calls(full_text)]
    W --> X[visible = strip_tool_blocks(full_text)]

    X --> Y{Narration only and not last step?}
    Y -- Yes --> P
    Y -- No --> Z{Flight hallucination guard triggered?}
    Z -- Yes --> P
    Z -- No --> AA{Tool calls found?}

    AA -- No --> AB[Final response path<br/>append assistant text to thread/messages<br/>yield done visible]
    AA -- Yes --> AC[Append assistant tool-call text to thread]
    AC --> AD[_check_tool_call_args(calls, thread)]

    AD --> AE{Clarification needed?}
    AE -- Yes --> AF[Return clarification done]
    AE -- No --> AG[_execute_tool_calls(calls, thread, messages)]

    AG --> AG1[For each call:<br/>normalize_arguments(call.arguments)]
    AG1 --> AG2{Call name}
    AG2 -- search_airports --> AG3[ToolExecutor.run search_airports]
    AG2 -- search_flights --> AG4[ToolExecutor.run search_flights]
    AG2 -- get_safety_assessment --> AG5[ToolExecutor.run get_safety_assessment]
    AG2 -- other --> AG6[ToolExecutor.run name,args]

    AG3 --> AH[Append tool result to thread/messages]
    AG4 --> AI[render_search_flights_result(result)]
    AG5 --> AJ[render_safety_result(result)]
    AG6 --> AH

    AI --> AK{Rendered final text?}
    AJ --> AL{Rendered final text?}
    AK -- Yes --> AM[Return done]
    AK -- No --> AN[Continue loop]
    AL -- Yes --> AM
    AL -- No --> AN
    AH --> AN
    AN --> P

    P --> AO{Max steps reached?}
    AO -- Yes --> AP[Return fallback asking for airport codes and date]

### Main stages
The pipeline starts with LocalToolAgent.run(messages), which emits an initial status event, determines flight and safety intent, and then routes the request into one of four paths: disabled-flight short-circuit, flight pre-resolution, safety short-circuit, or general/model handling. For non-flight/non-safety destination questions, it also checks a JSON-first country knowledge path before invoking the model, using _check_country_json() and optionally injecting _json_context as a synthetic system message.

### Flight path (if active)
For flight requests, the agent first tries to ground missing context before the LLM does anything expensive: _update_destination_from_chat(), _pre_resolve_destination(), _pre_resolve_origin(), and _pre_inject_date() enrich the thread with airport and date context derived from session state and chat. If enough information is grounded—at least two airport codes, at least one explicit date, and no prior search since the last user turn—the agent bypasses the model with _run_short_circuit(), calls search_flights across ranked destination candidates, optionally attaches per-airport safety briefs, and returns rendered multi-airport results.

### Safety path
For safety-only questions, the agent avoids the LLM entirely if it can resolve a location. It uses _run_safety_short_circuit(), prefers session-state destination values, falls back to _extract_safety_location() from the raw user message, then calls ToolExecutor.run("get_safety_assessment", ...) and formats the answer with render_safety_result(). If no location can be resolved, it falls through into the normal model path rather than failing immediately.

### Country JSON path
For destination knowledge queries like food, weather, surf, budget, safety, or broad country overviews, the agent checks _DESTINATION_KNOWLEDGE_RE and runs _check_country_json(latest_q) before model generation. That method uses _resolve_country_code() and _classify_query() to split requests into specific, broad, or followup: specific queries return a formatted JSON-backed answer immediately, while broad/follow-up queries store compact overview context in st.session_state["_json_context"] and inject it into the LLM thread as a system message.

### LLM loop
If no deterministic short-circuit finishes the turn, the request enters the bounded multi-step agent loop for step in range(settings.agent_max_steps). Each iteration recomputes grounded_codes, explicit_dates, and already_searched, optionally re-checks eligibility for flight short-circuiting, trims the thread with _trim_thread_to_fit(...), then calls self._model.stream_agent_turn(thread, tools=TOOLS) to generate the next assistant turn. The raw model output is split into full_text, parsed with parse_tool_calls(full_text), and cleaned for visible user text using strip_tool_blocks(full_text).

### Guards and tools
After each LLM turn, two guardrails can force another loop iteration instead of trusting the output: is_narration(visible) catches useless “I’m searching…” style text, and _FLIGHT_HALLUCINATION_RE catches fabricated flight results if no actual search_flights tool result exists yet. If the LLM emitted tool calls, the agent validates them with _check_tool_call_args(), which can trigger strict_airport_clarification() or strict_date_clarification(), and otherwise executes them through _execute_tool_calls().

### Tool execution
Inside _execute_tool_calls(), each tool call is normalized and run via ToolExecutor.run(name, args), with special-case handling for search_airports, search_flights, and get_safety_assessment. Tool results are appended to both thread and messages, and certain tool outputs can become final user-visible answers immediately through render_search_flights_result(result_str) or render_safety_result(result_str); if not, control returns to the loop for another LLM step.

### End conditions
The run ends in one of five ways: an early deterministic short-circuit, a JSON-specific answer, a rendered tool result, a plain final LLM response with no tool calls, or a max-step fallback asking for more specific airport/date details. The convenience wrapper run_collect(messages) simply consumes the event stream and returns the last "done" text.

### Project Elements

| Requirement | Location |
|------------|----------|
| **Data Cleaning** | `notebooks/01_data_cleaning/` — City safety cleaner, data merger, macro cleaner |
| **Exploratory Data Analysis** | `notebooks/02_exploratory_data_analysis/` — Distributions, world maps, country-level exploration |
| **Model / Pipeline Design and Building** | `notebooks/03_model_design_and_training/` + `app/models/safety/` — Feature engineering, MLP architecture, ensemble design |
| **Model Training** | `notebooks/03_model_design_and_training/` + `app/models/safety/v6_train.py` — PyTorch MLP and scikit-learn RF training |
| **Model Optimization** | `notebooks/04_model_optimization/` — Inference pipeline profiling and tuning |
| **Model / Pipeline Analysis and Discussion** | `notebooks/05_model_analysis_and_evaluation/` — Test predictions, error analysis, feature importance |

## Prerequisites

### Python (via Conda)
This project uses Python 3.12.8. Conda handles the version automatically.

If you are already using Anaconda or another conda distribution, skip to [Quick Setup](#quick-setup). Otherwise, install [Miniconda](https://docs.anaconda.com/miniconda/install/):

```bash
mkdir -p ~/miniconda3

# Apple Silicon (M1/M2/M3/M4)
curl https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh -o ~/miniconda3/miniconda.sh

# Intel Mac
curl https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh -o ~/miniconda3/miniconda.sh

bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm ~/miniconda3/miniconda.sh
source ~/miniconda3/bin/activate
conda init --all
```

You know conda is installed and working if you see `(base)` in your terminal prompt.

### Make
Usually pre-installed on macOS/Linux. Check with `make -v`. If not installed:
```bash
brew install make
```

### Docker
Required for the flight search API.

1. Install [Docker Desktop](https://docs.docker.com/get-docker/)
2. Verify: `docker --version`

## Quick Setup

```bash
# 1. Clone and enter the repo
git clone <your-repo-url>
cd wayfinder

# 2. Create the conda environment
make create
conda activate wayfinder

# 3. Start the flight API container
make docker-compose-up

# 4. Run the app
make run
```

On first launch, the Qwen 2.5 1.5B model (~3 GB) will be downloaded from HuggingFace automatically.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `localhost:8080` | Flight search API host |
| `API_BASE_SCHEME` | `http` | Flight API URL scheme |
| `WAYFINDER_DEVICE` | *(auto-detect)* | Force a compute device: `cuda`, `mps`, or `cpu` |
| `WAYFINDER_NO_MPS` | `false` | Set to `1` or `true` to skip MPS and fall back to CPU |

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make create` | Create the conda environment from `environment.yml` |
| `make update` | Update the conda environment from `environment.yml` |
| `make clean` | Remove the conda environment |
| `make activate` | Print the conda activate command (does **not** activate — you must run `conda activate wayfinder` yourself) |
| `make deactivate` | Deactivate the conda environment |
| `make run` | Start the Streamlit app |
| `make docker-compose-up` | Start the flight API Docker container |
| `make notebook` | Launch Jupyter Notebook |
| `make freeze` | Export installed packages to `environment.yml` |
| `make verify` | List conda environments to check the active one |

## Example Workflows

### First time setup
```bash
conda init --all
make create
conda activate wayfinder
make verify
python --version   # Should show 3.12.8
make docker-compose-up
make run
```

### Installing a new package
```bash
# Verify you're in the right environment
make verify

# Install via conda (preferred)
conda install <package_name>

# If you get a PackagesNotFoundError, use pip instead — conda will still
# track it in the environment properly
pip install <package_name>

# To remove a package
conda remove <package_name>
# or: pip uninstall <package_name>

# Export to environment.yml so teammates get it too
make freeze
```

### Daily development
```bash
# Before starting
git pull origin main
conda deactivate
make update
conda activate wayfinder
make docker-compose-up
make run

# After finishing
conda deactivate
make freeze   # only if you added/updated packages
git add .
git commit -m "your commit message"
git push origin <branch_name>
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
