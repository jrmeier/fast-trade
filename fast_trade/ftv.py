import json
import sys

import typer


app = typer.Typer(help="Fast Trade utilities", add_completion=False)


@app.callback()
def main_callback():
    """Utilities for Fast Trade."""


@app.command("convert")
def convert_cmd(
    src: str = typer.Argument(..., help="Source JSON/YAML file"),
    dest: str = typer.Argument(..., help="Destination JSON/YAML file"),
):
    if not (src.endswith((".json", ".yml", ".yaml")) and dest.endswith((".json", ".yml", ".yaml"))):
        raise typer.BadParameter("Source and destination must be .json/.yml/.yaml")

    if src.endswith((".yml", ".yaml")) or dest.endswith((".yml", ".yaml")):
        try:
            import yaml  # type: ignore
        except Exception:
            yaml = None
    else:
        yaml = None

    def dump_yaml(data, indent=0):
        pad = "  " * indent
        if isinstance(data, dict):
            lines = []
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{pad}{key}:")
                    lines.append(dump_yaml(value, indent + 1))
                else:
                    lines.append(f"{pad}{key}: {dump_yaml(value, 0).strip()}")
            return "\n".join(lines)
        if isinstance(data, list):
            lines = []
            for item in data:
                if isinstance(item, (dict, list)):
                    lines.append(f"{pad}-")
                    lines.append(dump_yaml(item, indent + 1))
                else:
                    lines.append(f"{pad}- {dump_yaml(item, 0).strip()}")
            return "\n".join(lines)
        if isinstance(data, str):
            if data == "" or ":" in data or "#" in data:
                return f"\"{data}\""
            return data
        if data is True:
            return "true"
        if data is False:
            return "false"
        if data is None:
            return "null"
        return str(data)

    with open(src, "r") as fh:
        if src.endswith((".yml", ".yaml")):
            if yaml is None:
                raise typer.BadParameter("PyYAML is required to read YAML inputs")
            data = yaml.safe_load(fh)
        else:
            data = json.load(fh)

    with open(dest, "w") as fh:
        if dest.endswith((".yml", ".yaml")):
            if yaml is not None:
                yaml.safe_dump(data, fh, sort_keys=False)
            else:
                fh.write(dump_yaml(data))
        else:
            json.dump(data, fh, indent=2)

    print(f"Converted {src} -> {dest}")


def main():
    try:
        app()
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
