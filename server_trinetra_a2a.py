"""Run Trinetra as an A2A agent that third-party agents can discover and call.

This is a separate entrypoint from server_trinetra.py on purpose. That one
serves the operator dashboard, which is a human-facing surface behind whatever
access control NTKMA puts in front of it. This one is a machine-facing surface
on the open agent network, and the two should be deployable, scalable and -
most importantly - restrictable independently.

The one piece of configuration that matters here is TRINETRA_A2A_PUBLIC_URL.
An A2A agent card advertises the URL peers should call back on, and a
container has no way to know the address a load balancer answers on. If it is
unset the card advertises the container's own bind address, which is correct
locally and useless in production. See deploy/ecs-express/trinetra-a2a/ for
how the deployment discovers the real endpoint and feeds it back in.
"""
from __future__ import annotations

import os

from trinetra.a2a.server import build_a2a_server


def main() -> None:
    host = os.environ.get("TRINETRA_A2A_HOST", "0.0.0.0")
    port = int(os.environ.get("TRINETRA_A2A_PORT", "9100"))
    public_url = os.environ.get("TRINETRA_A2A_PUBLIC_URL", "").strip() or None

    server = build_a2a_server(host=host, port=port, http_url=public_url)

    print(f"Trinetra A2A agent starting on {host}:{port}")
    if public_url:
        print(f"Advertising agent card at: {public_url.rstrip('/')}/.well-known/agent-card.json")
    else:
        print(
            "TRINETRA_A2A_PUBLIC_URL is not set - the agent card will advertise this container's "
            "own bind address. That is fine locally; behind a load balancer, peers will not be "
            "able to reach the address the card gives them."
        )
    server.serve()


if __name__ == "__main__":
    main()
