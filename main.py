import multiprocessing
import tkinter as tk
from ui.app import GeneradorApp

if __name__ == "__main__":
    # Obligatorio para PyInstaller --onefile en Windows: evita que cada proceso
    # hijo (ProcessPoolExecutor) relance la ventana principal de la app.
    multiprocessing.freeze_support()

    root = tk.Tk()
    app = GeneradorApp(root)
    root.mainloop()
