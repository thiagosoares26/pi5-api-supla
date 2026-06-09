import subprocess
import sys

print(f"O VS Code encontrou o Python em: {sys.executable}")
print("Forçando a instalação via subprocesso...")

# Pega o caminho absoluto exato e injeta o comando do pip
subprocess.check_call([sys.executable, "-m", "pip", "install", "pennylane", "numpy"])

print("\n✅ Instalação de QML concluída com sucesso! Pode deletar este arquivo.")