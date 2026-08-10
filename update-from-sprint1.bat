@echo off
cd /d %~dp0
echo Copiez votre ancien fichier mytree.db dans ce dossier avant de continuer.
pause
if not exist .venv py -m venv .venv
call .venv\Scripts\activate
python -m pip install -r requirements.txt
python -c "from app import init_db; init_db()"
echo Migration terminee sans suppression des anciennes donnees.
pause
