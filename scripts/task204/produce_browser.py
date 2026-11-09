import asyncio, json, os, sys, tempfile, time
from pathlib import Path
sys.path[:0] = ['/repo/backend', '/repo/scripts/task204']
from local_transport import LoopbackGuard
status = json.loads(Path('/evidence/status.private.local.json').read_text(encoding='utf-8-sig'))
private = json.loads(Path('/evidence/browser.private.local.json').read_text())
os.chdir(tempfile.mkdtemp(prefix='task204-producer-'))
os.environ.update(SUPABASE_URL='http://127.0.0.1:8000', SUPABASE_ANON_KEY=status['ANON_KEY'],
 SUPABASE_SERVICE_ROLE_KEY=status['SERVICE_ROLE_KEY'], GEMINI_API_KEY='',GEMINI_API_KEY_1='',GEMINI_API_KEY_2='',GEMINI_API_KEY_3='')
from app.core.database import get_service_role_client
from app.services.blueprint.producer import SourceArtifactRepository, ConfirmedArtifactProducer
from app.services.ai.gateway import RequestContext
from fake_algebra import FakeAlgebra
with LoopbackGuard() as guard:
 asyncio.run(ConfirmedArtifactProducer(SourceArtifactRepository(get_service_role_client()), FakeAlgebra()).resume(
  private['session_id'], RequestContext(time.monotonic()+60, lambda:None)))
 assert guard.blocked == 0
print('PASS: browser session canonical ready via fake algebra worker')
