#!/usr/bin/env python3
"""
Fusion 360 MCP Bridge

External Python bridge between generator scripts and Autodesk Fusion's official
local MCP endpoint.

Default endpoint:
    http://127.0.0.1:27182/mcp

Generator contract:
    def generate(params: dict[str, str]) -> str:
        return "<Fusion API Python source containing def run(context): ...>"
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_URL = os.environ.get("FUSION_MCP_URL", "http://127.0.0.1:27182/mcp")

PREFERRED_TOOL_NAMES = (
    "fusion_mcp_execute",
    "execute_api_script",
    "execute_script",
    "run_python_script",
    "run_api_script",
    "run_script",
)

PREFERRED_SCRIPT_ARGUMENTS = (
    "script",
    "code",
    "source",
    "python_code",
    "script_source",
    "python",
)


def _die(message: str, code: int = 2) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "input_schema", None)
    if isinstance(schema, dict):
        return schema

    schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict):
        return schema

    model_dump = getattr(tool, "model_dump", None)
    if callable(model_dump):
        data = model_dump(by_alias=False)
        if isinstance(data, dict):
            for key in ("input_schema", "inputSchema"):
                value = data.get(key)
                if isinstance(value, dict):
                    return value

    return {}


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", ""))


def _tool_description(tool: Any) -> str:
    return str(getattr(tool, "description", "") or "")


def _schema_properties(tool: Any) -> dict[str, Any]:
    props = _tool_schema(tool).get("properties", {})
    return props if isinstance(props, dict) else {}


def _is_string_schema(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == "string"


def choose_executor_tool(tools: list[Any], forced_name: str | None = None) -> Any:
    if not tools:
        raise RuntimeError("Fusion MCP nie zwrócił żadnych narzędzi.")

    if forced_name:
        for tool in tools:
            if _tool_name(tool) == forced_name:
                return tool
        available = ", ".join(sorted(_tool_name(t) for t in tools))
        raise RuntimeError(
            f"Nie znaleziono narzędzia '{forced_name}'. Dostępne: {available}"
        )

    by_name = {_tool_name(t): t for t in tools}
    for name in PREFERRED_TOOL_NAMES:
        if name in by_name:
            return by_name[name]

    ranked: list[tuple[int, Any]] = []
    for tool in tools:
        name = _tool_name(tool).lower()
        description = _tool_description(tool).lower()
        props = _schema_properties(tool)

        score = 0
        if "script" in name:
            score += 8
        if "python" in name:
            score += 5
        if "execute" in name or "run" in name:
            score += 4
        if "fusion" in description:
            score += 2
        if "python" in description:
            score += 4
        if "script" in description:
            score += 4

        for arg_name, arg_schema in props.items():
            if arg_name.lower() in PREFERRED_SCRIPT_ARGUMENTS and _is_string_schema(arg_schema):
                score += 10

        ranked.append((score, tool))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 10:
        available = ", ".join(sorted(_tool_name(t) for t in tools))
        raise RuntimeError(
            "Nie udało się pewnie rozpoznać narzędzia wykonującego skrypt. "
            f"Dostępne narzędzia: {available}. "
            "Uruchom 'tools' i wskaż nazwę przez --tool."
        )

    return ranked[0][1]


def choose_script_argument(tool: Any, forced_arg: str | None = None) -> str:
    props = _schema_properties(tool)

    if forced_arg:
        if props and forced_arg not in props:
            raise RuntimeError(
                f"Narzędzie '{_tool_name(tool)}' nie ma argumentu '{forced_arg}'. "
                f"Argumenty: {', '.join(props) or '(brak w schemacie)'}"
            )
        return forced_arg

    for candidate in PREFERRED_SCRIPT_ARGUMENTS:
        schema = props.get(candidate)
        if _is_string_schema(schema):
            return candidate

    required = _tool_schema(tool).get("required", [])
    if isinstance(required, list):
        string_required = [
            name for name in required
            if name in props and _is_string_schema(props[name])
        ]
        if len(string_required) == 1:
            return string_required[0]

    string_props = [name for name, schema in props.items() if _is_string_schema(schema)]
    if len(string_props) == 1:
        return string_props[0]

    raise RuntimeError(
        f"Nie udało się rozpoznać argumentu ze źródłem skryptu dla "
        f"'{_tool_name(tool)}'. Użyj --script-arg."
    )


def build_script_call(tool: Any, script: str, forced_arg: str | None = None) -> tuple[dict[str, Any], str]:
    props = _schema_properties(tool)
    name = _tool_name(tool)
    description = _tool_description(tool).lower()

    if "featureType" in props and "object" in props:
        looks_like_script_dispatcher = (
            name == "fusion_mcp_execute"
            or (
                "featuretype" in description
                and "script" in description
                and "object" in description
            )
        )
        if looks_like_script_dispatcher:
            return (
                {
                    "featureType": "script",
                    "object": {"script": script},
                },
                'featureType="script", object.script',
            )

    arg_name = choose_script_argument(tool, forced_arg)
    return ({arg_name: script}, arg_name)


def describe_script_call(tool: Any, forced_arg: str | None = None) -> str:
    props = _schema_properties(tool)
    name = _tool_name(tool)
    description = _tool_description(tool).lower()

    if "featureType" in props and "object" in props:
        looks_like_script_dispatcher = (
            name == "fusion_mcp_execute"
            or (
                "featuretype" in description
                and "script" in description
                and "object" in description
            )
        )
        if looks_like_script_dispatcher:
            return 'featureType="script", object.script'

    return choose_script_argument(tool, forced_arg)


def parse_params(items: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Parametr '{item}' musi mieć format nazwa=wartość.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Nieprawidłowy parametr: '{item}'.")
        params[key] = value.strip()
    return params


def load_generator(path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)

    module_name = f"fusion_generator_{path.stem}_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nie można załadować generatora: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generate = getattr(module, "generate", None)
    if not callable(generate):
        raise RuntimeError(
            f"Generator '{path}' musi definiować funkcję generate(params: dict) -> str."
        )
    return generate


def build_script_from_generator(path: Path, params: dict[str, str]) -> str:
    generate = load_generator(path)
    script = generate(params)
    if not isinstance(script, str) or not script.strip():
        raise RuntimeError("Generator nie zwrócił niepustego tekstu skryptu.")

    compile(script, f"<generated:{path.name}>", "exec")

    if "def run(" not in script:
        raise RuntimeError(
            "Wygenerowany skrypt nie zawiera funkcji run(context), wymaganej przez "
            "narzędzie wykonawcze Fusion."
        )

    return script


def result_to_text(result: Any) -> str:
    chunks: list[str] = []

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        try:
            chunks.append(json.dumps(structured, ensure_ascii=False, indent=2))
        except TypeError:
            chunks.append(str(structured))

    content = getattr(result, "content", None)
    if isinstance(content, list):
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                chunks.append(text)

    if not chunks:
        model_dump = getattr(result, "model_dump", None)
        if callable(model_dump):
            try:
                return json.dumps(model_dump(by_alias=False), ensure_ascii=False, indent=2)
            except TypeError:
                pass
        return str(result)

    return "\n".join(chunks)


class FusionBridge:
    def __init__(self, url: str):
        self.url = url
        self.client = None

    async def __aenter__(self) -> "FusionBridge":
        try:
            from mcp import Client
        except ImportError as exc:
            raise RuntimeError(
                "Brak pakietu 'mcp'. Zainstaluj zależności: "
                "python -m pip install -r requirements.txt"
            ) from exc

        self.client = Client(self.url)
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.client is not None:
            await self.client.__aexit__(exc_type, exc, tb)
            self.client = None

    async def list_tools(self) -> list[Any]:
        if self.client is None:
            raise RuntimeError("Bridge nie jest połączony.")

        tools: list[Any] = []
        cursor = None
        while True:
            result = await self.client.list_tools(cursor=cursor)
            tools.extend(result.tools)
            cursor = getattr(result, "next_cursor", None)
            if not cursor:
                break
        return tools

    async def execute_script(
        self,
        script: str,
        tool_name: str | None = None,
        script_arg: str | None = None,
    ) -> tuple[Any, Any, str]:
        if self.client is None:
            raise RuntimeError("Bridge nie jest połączony.")

        tools = await self.list_tools()
        tool = choose_executor_tool(tools, tool_name)
        payload, call_shape = build_script_call(tool, script, script_arg)

        result = await self.client.call_tool(
            _tool_name(tool),
            payload,
        )
        return result, tool, call_shape


async def command_tools(args) -> int:
    async with FusionBridge(args.url) as bridge:
        tools = await bridge.list_tools()

        print(f"Fusion MCP: {args.url}")
        print(f"Liczba narzędzi: {len(tools)}")
        for tool in tools:
            props = _schema_properties(tool)
            arg_desc = ", ".join(props.keys()) if props else "(brak/nieznany schemat)"
            print(f"- {_tool_name(tool)}  [{arg_desc}]")
            if args.verbose:
                desc = _tool_description(tool).strip().replace("\n", " ")
                if desc:
                    print(f"  {desc}")
        return 0


async def command_doctor(args) -> int:
    async with FusionBridge(args.url) as bridge:
        tools = await bridge.list_tools()
        tool = choose_executor_tool(tools, args.tool)
        call_shape = describe_script_call(tool, args.script_arg)

        protocol = getattr(bridge.client, "protocol_version", None)
        server_info = getattr(bridge.client, "server_info", None)
        server_name = getattr(server_info, "name", None) if server_info else None
        server_version = getattr(server_info, "version", None) if server_info else None

        print("OK: połączenie z Fusion MCP działa.")
        print(f"Endpoint: {args.url}")
        if protocol:
            print(f"Protokół MCP: {protocol}")
        if server_name or server_version:
            print(f"Serwer: {server_name or '?'} {server_version or ''}".rstrip())
        print(f"Narzędzia: {len(tools)}")
        print(f"Wykonawca skryptów: {_tool_name(tool)}")
        print(f"Wywołanie skryptu: {call_shape}")
        return 0


async def command_exec(args) -> int:
    path = Path(args.script).expanduser().resolve()
    if not path.is_file():
        _die(f"Nie znaleziono pliku skryptu: {path}")

    script = path.read_text(encoding="utf-8")
    compile(script, str(path), "exec")

    async with FusionBridge(args.url) as bridge:
        result, tool, call_shape = await bridge.execute_script(
            script, args.tool, args.script_arg
        )
        print(f"Tool: {_tool_name(tool)}")
        print(f"Tryb: {call_shape}")
        text = result_to_text(result)
        if text:
            print(text)
        return 1 if bool(getattr(result, "is_error", False)) else 0


async def command_run(args) -> int:
    generator_path = Path(args.generator).expanduser().resolve()
    try:
        params = parse_params(args.param)
        script = build_script_from_generator(generator_path, params)
    except Exception as exc:
        _die(str(exc))

    if args.save_generated:
        output = Path(args.save_generated).expanduser().resolve()
        output.write_text(script, encoding="utf-8")
        print(f"Zapisano wygenerowany skrypt: {output}")

    async with FusionBridge(args.url) as bridge:
        result, tool, call_shape = await bridge.execute_script(
            script, args.tool, args.script_arg
        )
        print(f"Generator: {generator_path.name}")
        print(f"Tool: {_tool_name(tool)}")
        print(f"Tryb: {call_shape}")
        text = result_to_text(result)
        if text:
            print(text)
        return 1 if bool(getattr(result, "is_error", False)) else 0


def command_emit(args) -> int:
    generator_path = Path(args.generator).expanduser().resolve()
    try:
        params = parse_params(args.param)
        script = build_script_from_generator(generator_path, params)
    except Exception as exc:
        _die(str(exc))

    output = Path(args.output).expanduser().resolve()
    output.write_text(script, encoding="utf-8")
    print(f"OK: zapisano {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Most Python -> oficjalny Autodesk Fusion MCP -> Fusion API"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Endpoint MCP (domyślnie: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--tool",
        default=None,
        help="Wymuś nazwę narzędzia wykonującego skrypt.",
    )
    parser.add_argument(
        "--script-arg",
        default=None,
        help="Wymuś nazwę argumentu, do którego trafia źródło Pythona.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="Sprawdź połączenie i wykonawcę skryptów.")
    p_doctor.set_defaults(handler=command_doctor)

    p_tools = sub.add_parser("tools", help="Wyświetl narzędzia odkryte dynamicznie.")
    p_tools.add_argument("-v", "--verbose", action="store_true")
    p_tools.set_defaults(handler=command_tools)

    p_exec = sub.add_parser("exec", help="Wyślij gotowy skrypt Fusion API do Fusion.")
    p_exec.add_argument("script", help="Plik .py z def run(context).")
    p_exec.set_defaults(handler=command_exec)

    p_run = sub.add_parser(
        "run",
        help="Uruchom generator, a jego wynik wyślij do Fusion.",
    )
    p_run.add_argument("generator", help="Plik generatora .py.")
    p_run.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAZWA=WARTOŚĆ",
        help="Parametr generatora; można podać wielokrotnie.",
    )
    p_run.add_argument(
        "--save-generated",
        default=None,
        metavar="PLIK.py",
        help="Opcjonalnie zapisz wygenerowany skrypt do pliku przed wysłaniem.",
    )
    p_run.set_defaults(handler=command_run)

    p_emit = sub.add_parser(
        "emit",
        help="Tylko wygeneruj skrypt do pliku; bez połączenia z Fusion.",
    )
    p_emit.add_argument("generator", help="Plik generatora .py.")
    p_emit.add_argument("output", help="Plik wyjściowy .py.")
    p_emit.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAZWA=WARTOŚĆ",
    )
    p_emit.set_defaults(handler=command_emit)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = args.handler(args)
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return int(result)
    except KeyboardInterrupt:
        print("\nPrzerwano.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
