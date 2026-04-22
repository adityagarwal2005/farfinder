# FarFinder v3

A intelligent flight search and multi-modal route builder that helps you find the best travel options across multiple airports and transportation modes.

## Features

- **Multi-Airport Search**: Find flights from nearby airports within a configurable radius
- **Flexible Search Options**: Search by date range, budget, or price trends
- **Route Building**: Generate multi-modal routes combining flights and ground transportation
- **Price Calendar**: View cheapest prices across calendar months
- **Natural Language Queries**: Ask FarFinder in plain English

## Tech Stack

- **Backend**: FastAPI (Python)
- **APIs**: 
  - Travelpayouts for flight data
  - OpenRouter for AI insights
  - Google Maps for geocoding
- **Frontend**: HTML, CSS, JavaScript

## Setup

### Prerequisites
- Python 3.8+
- pip

### Installation

1. Clone the repository
```bash
git clone https://github.com/adityagarwal2005/farfinder.git
cd farfinder/files
```

2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r ../requirements.txt
```

4. Create a `.env` file in the project root
```bash
cp ../.env.example .env
```

5. Add your API keys to `.env`:
   - `TRAVELPAYOUTS_TOKEN`: Get from https://travelpayouts.com
   - `OPENROUTER_API_KEY`: Get from https://openrouter.ai
   - `GOOGLE_MAPS_API_KEY`: Get from Google Cloud Console

### Running the Backend

```bash
cd files
uvicorn agent:app --reload --port 8001
```

The API will be available at `http://localhost:8001`

### Running the Frontend

Open `index.html` in your browser or serve it with a local server:
```bash
python -m http.server 8000
```

Then navigate to `http://localhost:8000`

## API Endpoints

- `POST /search`: Search flights with multi-airport support
- `POST /search/flexible`: Flexible date/budget search
- `POST /calendar`: Get monthly price calendar
- `POST /query`: Natural language search queries
- `GET /insights`: Get travel insights

## Project Structure

```
farfinder/
├── files/
│   ├── agent.py          # FastAPI main application
│   ├── airports.py       # Airport and location utilities
│   ├── flights.py        # Flight search and pricing
│   ├── routes.py         # Route building logic
│   ├── index.html        # Frontend UI
│   ├── script.js         # Frontend logic
│   └── style.css         # Frontend styles
├── requirements.txt      # Python dependencies
├── .env.example         # Example environment file
└── README.md            # This file
```

## License

MIT License
