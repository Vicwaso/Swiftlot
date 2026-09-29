"""Local launcher: isolated SQLite database, background worker, loopback-only web server."""
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent
venv=root/'.venv'
python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
env=os.environ.copy()
env.update(LOCAL_ONLY='true',DEBUG='true',PUBLIC_ORIGIN='http://127.0.0.1:8000')
def run(*args):
    subprocess.run([str(python),*args],cwd=root,env=env,check=True)

if __name__=='__main__':
    if not python.exists():
        subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
    dependencies=subprocess.run([str(python),'-c','import django, PIL, psycopg, pyotp, qrcode, cryptography, dj_database_url, dotenv, whitenoise'],capture_output=True)
    if dependencies.returncode:
        run('-m','pip','install','-r','requirements.lock')
    run('manage.py','migrate','--noinput')
    run('manage.py','bootstrap')
    run('manage.py','collectstatic','--noinput')
    print('\nConsumer website: http://127.0.0.1:8000/')
    print('Private staff login: http://127.0.0.1:8000/staff/login/')
    print('Use the one-time owner setup link printed above on your first run.')
    print('Keep this window open. Press Ctrl+C to stop.\n')
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    worker=subprocess.Popen([str(python),'manage.py','process_jobs','--loop'],cwd=root,env=env,creationflags=flags)
    try:
        run('manage.py','runserver','127.0.0.1:8000','--noreload')
    except KeyboardInterrupt:
        pass
    finally:
        worker.terminate()
        try: worker.wait(timeout=10)
        except subprocess.TimeoutExpired: worker.kill()
