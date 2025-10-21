"""HTTP proxy server for Factory Bridge"""

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import requests
from factory_bridge.config import (
    CLAUDE_MODELS,
    CLIPROXY_PORT,
    CUSTOM_PROMPT_CONFIG,
    FACTORY_CONFIG,
)


def generate_factory_config(port):
    """Generate Factory CLI config"""
    config = {
        "_comment": "Claude Code OAuth tokens work with Sonnet/Haiku models, but NOT with Opus",
        "custom_models": [
            {
                "model": model,
                "base_url": f"http://localhost:{port}",
                "api_key": "dummy-not-used",
                "provider": "anthropic",
            }
            for model in CLAUDE_MODELS
        ],
    }
    FACTORY_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    FACTORY_CONFIG.write_text(json.dumps(config, indent=2))
    print(f"Factory config: {FACTORY_CONFIG}")


class ProxyHandler(BaseHTTPRequestHandler):
    """Forward Factory requests to CLIProxyAPI"""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        logging.info(f"GET {self.path}")
        if self.path in ["/v1/models", "/models"]:
            models = [
                {"id": m, "object": "model", "provider": "anthropic"}
                for m in CLAUDE_MODELS
            ]
            self._send_json({"object": "list", "data": models})
        elif self.path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_error(404, "Not Found")

    def do_POST(self):
        logging.info(f"POST {self.path}")
        if self.path == "/v1/messages":
            self._handle_claude()
        else:
            self._send_error(404, "Not Found")

    def _handle_claude(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request_data = json.loads(body)
            is_streaming = request_data.get("stream", False)
            self._modify_system_prompt(request_data)
            self._adjust_max_tokens(request_data)
            system_prompt = request_data.get("system", "")
            if isinstance(system_prompt, list):
                system_length = sum(
                    len(block.get("text", ""))
                    for block in system_prompt
                    if block.get("type") == "text"
                )
            else:
                system_length = len(system_prompt)
            logging.info(
                f"Forwarding request with system prompt length: {system_length} chars"
            )
            cliproxy_url = f"http://localhost:{CLIPROXY_PORT}/v1/messages"
            if is_streaming:
                response = requests.post(
                    cliproxy_url,
                    headers={"Content-Type": "application/json", "Connection": "close"},
                    json=request_data,
                    stream=True,
                    timeout=30,
                )
                if response.status_code != 200:
                    error_content = response.content
                    status_code = self._handle_error_response(
                        error_content, response.status_code
                    )
                    self.send_response(status_code)
                    for key, value in response.headers.items():
                        if key.lower() not in ["transfer-encoding", "content-encoding"]:
                            self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(error_content)
                    return
                self.send_response(response.status_code)
                for key, value in response.headers.items():
                    if key.lower() not in ["transfer-encoding", "content-encoding"]:
                        self.send_header(key, value)
                self.end_headers()
                buffer = b""
                try:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            buffer += chunk
                            self.wfile.write(chunk)
                            if (
                                b'"type":"message_stop"' in buffer
                                or b'"type": "message_stop"' in buffer
                            ):
                                response.close()
                                return
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    try:
                        response.close()
                    except Exception:
                        pass
            else:
                response = requests.post(
                    cliproxy_url,
                    headers={"Content-Type": "application/json"},
                    json=request_data,
                    timeout=120,
                )
                if response.status_code != 200:
                    status_code = self._handle_error_response(
                        response.content, response.status_code
                    )
                    self.send_response(status_code)
                else:
                    self.send_response(response.status_code)
                for key, value in response.headers.items():
                    if key.lower() not in ["transfer-encoding", "content-encoding"]:
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(response.content)
        except Exception as e:
            logging.exception(f"Unexpected error in _handle_claude: {e}")
            self._send_error(500, str(e))

    def _handle_error_response(self, error_content, original_status):
        """Parse error response and return appropriate status code"""
        try:
            error_data = json.loads(error_content)
            error_type = error_data.get("error", {}).get("type", "")
            error_message = error_data.get("error", {}).get("message", "")
            if error_type == "rate_limit_error":
                logging.warning(f"Rate limit exceeded: {error_message}")
                return 429
            elif error_type == "authentication_error":
                logging.error(
                    f"Rate limit or Auth error (check yourself): {error_message}"
                )
                return 401
            else:
                logging.error(f"API error ({error_type}): {error_message}")
                return original_status
        except (json.JSONDecodeError, KeyError, AttributeError):
            logging.error(f"Could not parse error response: {error_content[:500]}")
            return original_status

    def _adjust_max_tokens(self, request_data):
        """Adjust max_tokens based on model limits"""
        max_tokens = request_data.get("max_tokens", 0)
        max_limit = 8192
        if max_tokens > max_limit:
            request_data["max_tokens"] = max_limit

    def _modify_system_prompt(self, request_data):
        """Modify system prompt based on custom config"""
        if not CUSTOM_PROMPT_CONFIG.exists():
            return
        try:
            config = json.loads(CUSTOM_PROMPT_CONFIG.read_text())
            mode = config.get("mode", "replace")
            original_system = request_data.get("system", "")
            # Normalize original to list of blocks
            if isinstance(original_system, str):
                original_blocks = [{"type": "text", "text": original_system}]
            elif isinstance(original_system, list):
                original_blocks = original_system
            else:
                original_blocks = []
            original_prompt = "\n\n".join(
                [
                    block.get("text", "")
                    for block in original_blocks
                    if block.get("type") == "text"
                ]
            )
            logging.debug(
                f"Original system prompt length: {len(original_prompt)} chars"
            )
            custom_prompt = None
            if "prompt_file" in config:
                prompt_file = Path(config["prompt_file"]).expanduser()
                if prompt_file.exists():
                    custom_prompt = prompt_file.read_text().strip()
                else:
                    logging.warning(f"Custom prompt file not found: {prompt_file}")
                    return
            elif "prompt" in config:
                custom_prompt = config["prompt"].strip()
            else:
                logging.warning("No custom prompt specified in config")
                return
            if mode == "replace":
                system_blocks = [
                    {
                        "type": "text",
                        "text": custom_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
                request_data["system"] = system_blocks
                logging.info(
                    f"Applied custom system prompt (replace mode, {len(custom_prompt)} chars) with cache_control"
                )
            elif mode == "append":
                append_block = {
                    "type": "text",
                    "text": f"\n\n{custom_prompt}",
                    "cache_control": {"type": "ephemeral"},
                }
                system_blocks = original_blocks + [append_block]
                request_data["system"] = system_blocks
                logging.info(
                    f"Applied custom system prompt (append mode, {len(custom_prompt)} chars) with cache_control"
                )
            else:
                logging.warning(f"Unknown prompt mode: {mode}")
        except Exception as e:
            logging.error(f"Error modifying system prompt: {e}")

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        error = {"error": {"message": message, "code": code}}
        self.wfile.write(json.dumps(error).encode())


def run_server(port):
    """Run the proxy server"""
    server = HTTPServer(("0.0.0.0", port), ProxyHandler)

    print("")
    print("  _____          _                    ____       _     _")
    print(" |  ___|_ _  ___| |_ ___  _ __ _   _ | __ ) _ __(_) __| | __ _  ___")
    print(" | |_ / _` |/ __| __/ _ \\| '__| | | ||  _ \\| '__| |/ _` |/ _` |/ _ \\")
    print(" |  _| (_| | (__| || (_) | |  | |_| || |_) | |  | | (_| | (_| |  __/")
    print(
        " |_|  \\__,_|\\___|\\__\\___/|_|   \\__, ||____/|_|  |_|\\__,_|\\__, |\\___|"
    )
    print("                                |___/                     |___/")
    print(f"\nProxy: http://localhost:{port}")
    print(f"Config: {FACTORY_CONFIG}")
    print(f"Models: {', '.join(CLAUDE_MODELS)}")
    print("\nPress Ctrl+C to stop\n")

    logging.info(f"Proxy server listening on port {port}")
    logging.info(f"CLIProxyAPI running on port {CLIPROXY_PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        logging.info("Server shutting down")
        server.shutdown()
