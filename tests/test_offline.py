import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeExecuteTool:
    name = "fusion_mcp_execute"
    description = """
    Execute operations.
    featureType: "script"
    object: {"script": Python script content}
    """
    input_schema = {
        "type": "object",
        "properties": {
            "featureType": {"type": "string"},
            "object": {"type": "object"},
        },
        "required": ["featureType", "object"],
    }


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = load_module(ROOT / "fusion_bridge.py", "fusion_bridge_test")

    def test_current_fusion_dispatch_payload(self):
        script = "def run(_context: str):\n    print('OK')\n"
        payload, shape = self.bridge.build_script_call(FakeExecuteTool(), script)

        self.assertEqual(payload["featureType"], "script")
        self.assertEqual(payload["object"]["script"], script)
        self.assertEqual(shape, 'featureType="script", object.script')

    def test_current_tool_is_preferred(self):
        tool = self.bridge.choose_executor_tool([FakeExecuteTool()])
        self.assertEqual(tool.name, "fusion_mcp_execute")


class GeneratorTests(unittest.TestCase):
    def compile_generated(self, relpath, params=None):
        params = params or {}
        module_name = str(relpath).replace("/", "_").replace("\\", "_").replace(".", "_")
        module = load_module(ROOT / relpath, module_name)
        script = module.generate(params)
        compile(script, f"<{relpath}>", "exec")
        self.assertIn("def run(", script)
        return module, script

    def test_block(self):
        self.compile_generated(
            pathlib.Path("generators/generator_test_block.py"),
            {"width_mm": "50", "depth_mm": "25", "height_mm": "8"},
        )

    def test_laser_plate(self):
        self.compile_generated(
            pathlib.Path("generators/generator_laser_plate.py"),
            {"kerf_mm": "0.15"},
        )

    def test_box_joint_v3(self):
        module, script = self.compile_generated(
            pathlib.Path("generators/generator_box_joint_3mm_v3.py"),
            {"include_lid": "1"},
        )
        layout = module.build_layout({})
        self.assertEqual(len(layout["panels"]), 6)
        self.assertIn("previous.endSketchPoint", script)
        self.assertIn("first_line.startSketchPoint", script)

    def test_box_joint_v3_without_lid(self):
        module, _ = self.compile_generated(
            pathlib.Path("generators/generator_box_joint_3mm_v3.py"),
            {"include_lid": "0"},
        )
        layout = module.build_layout({"include_lid": "0"})
        self.assertEqual(len(layout["panels"]), 5)

    def test_box_joint_v4_compiles(self):
        self.compile_generated(
            pathlib.Path("generators/generator_box_joint_3d_v4.py"),
            {},
        )


if __name__ == "__main__":
    unittest.main()
