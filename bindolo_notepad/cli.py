from bindolo_notepad import create_app as bindolo


def run():
  print("waitress-serve --call bindolo_notepad.create_app")


if __name__ == "__main__":
  run()
