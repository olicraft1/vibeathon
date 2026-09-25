"""CharlaViva command line: serve, demo, doctor."""

from __future__ import annotations

import argparse
import asyncio
import sys


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app
    from .session import SessionManager, demo_session_specs

    manager = SessionManager()
    demo_specs = demo_session_specs(args.sessions) if args.demo else None
    if demo_specs:
        print(f"🎬 demo sessions: {len(demo_specs)} stages (looped samples)")
    app = create_app(manager, demo_specs=demo_specs)

    print(f"\n  🧉 CharlaViva — live captions for conferences")
    print(f"  ─────────────────────────────────────────────")
    print(f"  👥 Audience view:   http://{args.host}:{args.port}/")
    print(f"  🎛️  Production:      http://{args.host}:{args.port}/admin")
    print(f"  🎥 OBS overlay:     http://{args.host}:{args.port}/overlay?session=SESSION_ID&lang=es")
    print(f"  ─────────────────────────────────────────────\n")

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


def _doctor(args: argparse.Namespace) -> int:
    from .config import SAMPLES_DIR, Settings, resolve_engine

    settings = Settings.from_env()
    ok = True

    def check(label: str, good: bool, hint: str = "", required: bool = True) -> None:
        nonlocal ok
        mark = "✅" if good else ("⚠️ " if required else "ℹ️ ")
        print(f"  {mark} {label}" + (f" — {hint}" if hint and not good else ""))
        if required:
            ok = ok and good

    print("\n🧉 CharlaViva doctor")
    check(f"python {sys.version.split()[0]}", sys.version_info >= (3, 10), "need 3.10+")

    for mod in ("fastapi", "uvicorn", "av", "numpy", "google.genai"):
        try:
            __import__(mod)
            check(f"{mod} installed", True)
        except ImportError:
            check(f"{mod} installed", False, "pip install -r requirements.txt")

    try:
        import faster_whisper  # noqa: F401

        check("faster-whisper (local ASR) installed", True)
    except ImportError:
        check("faster-whisper (local ASR) installed", False, "pip install faster-whisper")

    check(
        "GEMINI_API_KEY set (optional)",
        bool(settings.gemini_api_key),
        "only needed for the gemini engine / EN→ES translation",
        required=False,
    )
    check(
        "sample talks present",
        (SAMPLES_DIR / "talk_en.mp3").exists() and (SAMPLES_DIR / "talk_es.mp3").exists(),
        "git checkout should include samples/",
    )
    print(f"\n  engine for this environment: {resolve_engine(settings)}\n")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="charlaviva",
        description="CharlaViva — open source live captions & simultaneous translation",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the caption server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--demo", action="store_true", help="preload the sample stages")
    p_serve.add_argument("--sessions", type=int, default=2, help="demo stages to start (1-3)")
    p_serve.add_argument("--log-level", default="info")

    p_demo = sub.add_parser(
        "demo", help="serve + the bundled sample talks as looping live stages"
    )
    p_demo.add_argument("--host", default="0.0.0.0")
    p_demo.add_argument("--port", type=int, default=8000)
    p_demo.add_argument("--sessions", type=int, default=2, help="stages to start (1-3)")
    p_demo.add_argument("--log-level", default="info")

    sub.add_parser("doctor", help="check installation & configuration")

    args = parser.parse_args(argv)
    if args.command in ("serve", "demo"):
        if args.command == "demo":
            args.demo = True
        return _serve(args)
    if args.command == "doctor":
        return _doctor(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
