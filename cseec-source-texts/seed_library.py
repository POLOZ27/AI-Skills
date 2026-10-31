"""Fill the local public-domain library once (run inside the Open WebUI container).

    docker cp cseec-source-texts school-ai-openwebui:/tmp/
    docker exec school-ai-openwebui python /tmp/cseec-source-texts/seed_library.py

Downloads the 146 Library of Congress Aesop fables (about 1 MB, one page per second)
and Project Gutenberg's title catalogue (titles and authors only, not the books).
Running it again only fills in what is missing and refreshes the catalogue.
"""

import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location(
    "cseec_source_texts", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cseec_source_texts.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(module.seed(), ensure_ascii=False))
