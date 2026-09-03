# Architecture

```text
external generator
      |
      | generate(params) -> Python source
      v
fusion_bridge.py
      |
      | MCP Streamable HTTP
      v
http://127.0.0.1:27182/mcp
      |
      v
fusion_mcp_execute
      |
      | featureType="script"
      | object={"script": "..."}
      v
Fusion API
      |
      v
active Fusion document
```

Geometry generation stays outside the Fusion process. The bridge only transports generated Fusion API scripts through MCP.
