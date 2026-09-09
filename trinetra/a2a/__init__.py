"""Agent2Agent (A2A) interoperability for Trinetra.

Two directions, deliberately asymmetric in how much they trust each other:

- `server.py` exposes Trinetra to third-party agents over the A2A protocol,
  publishing an agent card that declares what it can and cannot do.
- `client.py` lets Trinetra consult third-party agents, and treats everything
  they say as untrusted input - see `trust.py` for why that is not paranoia.
"""
