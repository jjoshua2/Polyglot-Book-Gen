# Polyglot-Book-Gen
Generates chess opening books in polyglot format using imported PGN games and UCI engine analysis

Edit engineLocation = "C:\Stockfish_16090309_520_x64_modern_BYO_RW" to be your UCI engine of choice.

Edit 
engine.setoption({"Hash": 2048, "Threads": 4, "SyzygyPath": "C:\TB;E:\TB\wdl;E:\TB\dtz"}) with your engines's options.

Edit E:\pgn\*.pgn to be your pgn folder of hundreds or tens of thousands of strong games, depending on how big of a book, and how long you want it to think.

Edit fixedDepth = 27 for how deep you want each move searched.

Run with python create.py
