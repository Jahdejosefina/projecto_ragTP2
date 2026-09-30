"""
Builds a certificate bundle that includes the ones from the Windows store.

    python tools/ca_bundle_windows.py

Writes `.certs/ca_bundle.pem`. `environment.py` picks it up automatically on import;
there's nothing to export by hand.

WHAT THIS IS FOR
-----------------
Behind a proxy that inspects TLS (common at companies, some campuses) downloading a model
from HuggingFace fails with

    SSL: CERTIFICATE_VERIFY_FAILED - self-signed certificate in certificate chain

The site isn't blocked: the proxy re-signs the connection with its own root certificate.
That certificate IS in the Windows store (which is why the browser works) but NOT in
certifi's bundle, which is what `requests` and `huggingface_hub` use.

THIS DOES NOT DISABLE VERIFICATION. It merges certifi's certificates with Windows' trusted
roots into one PEM file, and full chain verification still happens against it.

One-line alternative, if you'd rather install one more package:
    pip install truststore   and   truststore.inject_into_ssl()
"""

import os
import ssl
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINATION = os.path.join(ROOT, ".certs", "ca_bundle.pem")


def windows_certificates():
    """The trusted root and intermediate certificates from the Windows store, in PEM."""
    pems, seen = [], set()
    for store in ("ROOT", "CA"):
        try:
            for cert_bytes, cert_type, trust in ssl.enum_certificates(store):
                # trust is True (all uses) or a set of OIDs; False means "don't trust"
                if trust is False or cert_type != "x509_asn" or cert_bytes in seen:
                    continue
                seen.add(cert_bytes)
                pems.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
        except Exception as e:
            print(f"  warning: couldn't read store '{store}': {type(e).__name__}: {e}")
    return pems


def main():
    if sys.platform != "win32":
        print("This only does something on Windows. Elsewhere the system store is already used,")
        print("or export SSL_CERT_FILE yourself.")
        return 1

    import certifi

    base = open(certifi.where(), "r", encoding="utf-8").read()
    extra = windows_certificates()
    print(f"certifi                    : {certifi.where()}")
    print(f"Windows certificates found : {len(extra)}")

    os.makedirs(os.path.dirname(DESTINATION), exist_ok=True)
    with open(DESTINATION, "w", encoding="utf-8", newline="\n") as f:
        f.write(base if base.endswith("\n") else base + "\n")
        f.write("\n# ---- certificates from the Windows store ----\n")
        f.write("\n".join(extra))
    print(f"written                    : {DESTINATION} ({os.path.getsize(DESTINATION):,} bytes)")
    print("environment.py uses it automatically from the next `import environment` on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
