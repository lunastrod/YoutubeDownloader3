# pruebasTkinter

crear vnev
python -m venv .venv

activar venv
.venv\Scripts\activate

actualizar requirements
pip freeze > requirements.txt

instalar requirements
pip install -r requirements.txt

compilar en un exe
pyinstaller --noconsole --onefile --collect-all customtkinter --distpath . src/main.py

borrar ficheros de compilacion
Remove-Item -Recurse -Force build, *.spec, *.exe