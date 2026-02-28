# Personalized Chess Coach

AI-powered chess game analysis tool that provides personalized feedback using Stockfish and LLMs.

## Features

- 🎯 **Smart Analysis**: Combines Stockfish engine with AI explanations
- 🎓 **Personalized Feedback**: Tailored to your skill level
- 📊 **Pattern Recognition**: Identifies recurring mistakes
- 💡 **Learning Focus**: Suggests specific areas for improvement
- 🖥️ **CLI Interface**: Easy-to-use command-line tool

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd personalized-chess-coach
```

2. Create virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install poetry
poetry install
```

3. Configure environment variables:
```bash
cp .env .env
# Edit .env with your API keys
```

## Usage

### Analyze a single game
```bash
chess-coach analyze game.pgn
```

### Analyze with specific skill level
```bash
chess-coach analyze game.pgn --skill-level 1500
```

### Interactive mode
```bash
chess-coach interactive
```

### Set default LLM provider
```bash
chess-coach config set-llm openai gpt-4
```

## Configuration

Edit `.env` file to configure:
- API keys for LLM providers (OpenAI, Anthropic)
- Stockfish settings (depth, time limit)
- Data directories

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black .

# Lint code
poetry run ruff check .
```

## License

MIT License
