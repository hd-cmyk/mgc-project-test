from __future__ import annotations

import argparse

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TCR Agent Web GUI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    try:
        import uvicorn
        import fastapi  # noqa: F401
    except ImportError:
        from tcr_agent.web_fallback import run_fallback

        run_fallback(args.host, args.port)
        return
    uvicorn.run("tcr_agent.web_app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
