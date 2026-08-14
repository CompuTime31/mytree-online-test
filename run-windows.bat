@echo off
cd /d %~dp0
if not exist .venv py -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -c "from app import init_db; init_db()"
set MYTREE_SECRET=change-this-secret-before-internet
echo.
echo MyTree Professional v1.8.0 RC1 Rev.13 : http://localhost:8080
echo Compte initial : admin / admin123
echo Pour le telephone, utilisez http://ADRESSE_IP_DU_PC:8080
waitress-serve --listen=0.0.0.0:8080 app:app
pause
