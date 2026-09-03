# Fusion 360 MCP Bridge

Python bridge for Autodesk Fusion's official local MCP server, with example geometry generators for Fusion API.

> Status: tested locally with Fusion MCP endpoint `http://127.0.0.1:27182/mcp`.

Projekt powstał jako prosty most:

**generator Python → bridge MCP → oficjalny Fusion MCP → Fusion API → geometria w Fusion**

Repo jest nastawione na generatory CAD/CAM, szczególnie pod cięcie laserowe.

## Co działa

- połączenie z oficjalnym lokalnym serwerem Fusion MCP,
- dynamiczne wykrywanie narzędzi,
- obsługa aktualnego dispatchera `fusion_mcp_execute`,
- wykonywanie skryptów Fusion API z `run(_context)`,
- generatory jako niezależne moduły Python,
- testowa bryła 3D,
- płaski panel pod laser,
- box-joint / finger-joint do DXF,
- eksperymentalne złożenie box-joint 3D.

## Wymagania

- Autodesk Fusion desktop,
- włączony **Fusion MCP Server**,
- Python 3.10+,
- pakiet Python `mcp` v2.

Domyślny endpoint:

`http://127.0.0.1:27182/mcp`

## Instalacja

### Windows / PowerShell

```powershell
git clone https://github.com/filipescu88/fusion360-mcp-bridge.git
cd fusion360-mcp-bridge

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Alternatywnie:

```powershell
pip install -e .
```

## Włączenie MCP w Fusion

W Fusion:

`Preferences → General → API → Fusion MCP Server`

Fusion musi być uruchomiony, gdy używasz bridge'a.

## Test połączenia

```powershell
python fusion_bridge.py doctor
```

Przykładowy poprawny wynik:

```text
OK: połączenie z Fusion MCP działa.
Endpoint: http://127.0.0.1:27182/mcp
Wykonawca skryptów: fusion_mcp_execute
Wywołanie skryptu: featureType="script", object.script
```

Lista narzędzi:

```powershell
python fusion_bridge.py tools -v
```

## Architektura

Aktualny Fusion MCP udostępnia dispatcher:

```text
fusion_mcp_execute
```

Dla skryptu Python bridge wysyła logicznie:

```text
featureType = "script"
object.script = "<wygenerowany kod Fusion API>"
```

Bridge wykrywa ten wariant automatycznie.

Generator nie musi komunikować się z MCP. Jego jedynym zadaniem jest zwrócić tekst kompletnego skryptu Fusion API.

Kontrakt generatora:

```python
def generate(params: dict[str, str]) -> str:
    ...
```

Wygenerowany skrypt musi zawierać:

```python
def run(_context: str):
    ...
```

## Generatory

### 1. Testowa bryła

```powershell
python fusion_bridge.py run generators/generator_test_block.py
```

Domyślnie tworzy prostopadłościan 40 × 30 × 10 mm.

### 2. Panel do lasera

```powershell
python fusion_bridge.py run generators/generator_laser_plate.py
```

Domyślnie:

- 120 × 80 mm,
- 4 otwory Ø5,
- centralne wycięcie 40 × 12 mm,
- opcjonalna kompensacja kerfu.

Przykład:

```powershell
python fusion_bridge.py run generators/generator_laser_plate.py `
  --param width_mm=200 `
  --param height_mm=120 `
  --param hole_diameter_mm=6 `
  --param hole_edge_mm=15 `
  --param kerf_mm=0.15
```

Po wygenerowaniu:

`PPM na szkicu → Export DXF`

### 3. Box-joint / finger-joint — stabilny

```powershell
python fusion_bridge.py run generators/generator_box_joint_3mm_v3.py
```

Domyślnie tworzy 6 zamkniętych profili pudełka pod sklejkę 3 mm.

Wersja V3 używa topologicznego łączenia odcinków przez istniejące `SketchPoint`, co jest istotne dla poprawnego tworzenia zamkniętych profili w Fusion.

Przykład:

```powershell
python fusion_bridge.py run generators/generator_box_joint_3mm_v3.py `
  --param box_width_mm=200 `
  --param box_depth_mm=120 `
  --param box_height_mm=80 `
  --param material_mm=3 `
  --param kerf_mm=0.15 `
  --param clearance_mm=0.05
```

Bez wieka:

```powershell
python fusion_bridge.py run generators/generator_box_joint_3mm_v3.py `
  --param include_lid=0
```

### 4. Box-joint 3D — experimental

```powershell
python fusion_bridge.py run generators/experimental/generator_box_joint_3d_v4.py
```

Cel tej wersji:

- zachować layout 2D do DXF,
- wyekstrudować panele,
- utworzyć osobne komponenty,
- ustawić je jako złożone pudełko.

Ta wersja pozostaje w `experimental`, dopóki nie zostanie szerzej przetestowana na realnych dokumentach Fusion.

## Własny generator

Najprostszy szkielet:

```python
def generate(params: dict[str, str]) -> str:
    return '''
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("Open a Design document first.")

    print("OK")
'''.lstrip()
```

Uruchomienie:

```powershell
python fusion_bridge.py run moj_generator.py
```

## Emitowanie skryptu bez Fusion

```powershell
python fusion_bridge.py emit generators/generator_laser_plate.py generated.py
```

## Testy offline

Bez uruchamiania Fusion:

```powershell
python -m unittest discover -s tests -v
```

Testy sprawdzają:

- payload dla `fusion_mcp_execute`,
- składnię generowanych skryptów,
- podstawowe warianty generatorów.

## Ważne przy dużych szkicach

Przy setkach odcinków warto korzystać z:

```python
sketch.isComputeDeferred = True
```

na czas tworzenia geometrii i bezwzględnie przywrócić:

```python
sketch.isComputeDeferred = False
```

Istotne jest też łączenie kolejnych odcinków przez istniejące `SketchPoint`, zamiast polegania wyłącznie na identycznych współrzędnych `Point3D`.

## Laser / kerf

Nie wpisuj losowej wartości kerfu.

Najpierw zmierz:

- rzeczywistą grubość materiału,
- szerokość szczeliny cięcia dla konkretnej mocy i posuwu,
- potrzebny luz montażowy.

Jeżeli CAM lub kontroler już kompensuje kerf, zostaw kompensację generatora wyłączoną.

## Oficjalne źródła

Autodesk Fusion MCP:

- https://help.autodesk.com/view/fusion360/ENU/?guid=FMCP-OVERVIEW
- https://help.autodesk.com/view/ADSKMCP/ENU/?guid=ADSKMCP_FusionDesktopMcp_connecting_to_the_fusion_mcp_server_html

Fusion API:

- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SketchLines_addByTwoPoints.htm
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Sketch_isComputeDeferred.htm
- https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/ExtrudeFeatures_addSimple.htm

MCP Python SDK:

- https://github.com/modelcontextprotocol/python-sdk

Referencyjny projekt Autodesk Fusion:

- https://github.com/AutodeskFusion360/FusionMCPSample

## Bezpieczeństwo

Bridge wykonuje kod Python **wewnątrz aktywnej sesji Fusion**.

Uruchamiaj tylko generatory, którym ufasz.

## License

MIT
