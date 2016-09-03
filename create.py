from struct import pack
import chess.pgn
import chess.uci
import chess.uci
import glob
import pickle
import signal
import sys

ideaDepth = 30 #in fullmove_number
fixedDepth = 27
old=111
new=old+1
input = 'tree' + str(old) + '.data'
out = 'tree' + str(new) + '.data'
inanalysis = 'analysis' + str(old) + '.data'
outanalysis = 'analysis' + str(new) + '.data'
bookFile = 'book' + str(new) + '.bin'
engineLocation = "C:\Stockfish_16090309_520_x64_modern_BYO_RW"
#engineLocation = "C:\Stockfish_16071200_520_x64_modern_BYO_MF_RW"

class Node(object):	
	def __init__(self, fen, zobrist_hash, move):
		self.fen = fen
		self.zobrist_hash = zobrist_hash
		self.move = move
						
		self.children = []		
		self.public = 0
		self.ia = None
		self.depth = None
		self.score = None		
	def add(self, fen, zobrist_hash, polymove):
		for c in self.children:
			if c.zobrist_hash == (zobrist_hash):				
				return (c,polymove)
		self.children.append(Node(fen, zobrist_hash, polymove))		
		return (self.children[-1], polymove)
	
with open(input, 'rb') as input:
	global root
	root = pickle.load(input)
	print("tree loaded!")
#root = Node(chess.STARTING_FEN, chess.Board().zobrist_hash(), None)
#root.public = 1
analysis = {}
with open(inanalysis, 'rb') as input:	
	analysis = pickle.load(input)
	print("analysis loaded!")

def recurseSaveAnalysis(currentRoot):
	global analysis
	if currentRoot.ia != None:
		analysis[currentRoot.fen] = (currentRoot.ia, currentRoot.depth)
	for child in currentRoot.children:
		recurseSaveAnalysis(child)

def saveAnalysis():
	#recurseSaveAnalysis(root)
	with open(outanalysis, 'wb') as output:
		print("beginning analysis dump")
		pickle.dump(analysis, output, pickle.HIGHEST_PROTOCOL)
		print("saved analysis")
		
def save():
	saveAnalysis()
	with open(out, 'wb') as output:
		print("beginning dump")
		pickle.dump(root, output, pickle.HIGHEST_PROTOCOL)
		
def Exit_gracefully(signal, frame):	
	save()
	sys.exit(0)

def convertMovetoPmove(fen, move):
	if move.promotion:
		polymove = (move.promotion-1) << 12 | move.to_square | move.from_square << 6
	else:		
		if move.from_square == chess.E1 or move.from_square == chess.E8 and chess.Board(fen).is_castling(move):			
			if move.to_square == chess.G1: #white castles
				move.to_square = chess.H1				
			elif move.to_square == chess.C1:
				move.to_square = chess.A1				
				
			elif move.to_square == chess.G8: #black castles
				move.to_square = chess.H8
			elif move.to_square == chess.C8:
				move.to_square = chess.A8
		polymove = move.to_square | move.from_square << 6
	return polymove
	
def createTree(fileName):
	pgn = open(fileName, encoding="utf8")
	game = chess.pgn.read_game(pgn)
	while(game and not game.is_end()):
		global root
		root.public += 1
		next_move = game.variations[0]
		next_board = next_move.board()
		fen = next_board.fen()		
		pmove = convertMovetoPmove(root.fen, next_move.move)		
		currentRoot = root.add(fen, next_board.zobrist_hash(), pmove)[0]
		currentRoot.public += 1
		while(not next_move.is_end() and next_move.board().fullmove_number <= ideaDepth):
			next_move = next_move.variations[0]
			next_board = next_move.board()
			
			pmove = convertMovetoPmove(fen, next_move.move)			
			fen = next_board.fen()
			currentRoot = currentRoot.add(fen, next_board.zobrist_hash(), pmove)[0]
			currentRoot.public += 1
		game = chess.pgn.read_game(pgn)

def childrenScored(currentRoot):
	for child in currentRoot.children:
		if child.score == None:
			return False
	return True
		
moves = {}
def recurseWriteBook(currentRoot, depth):
	#if depth <= ideaDepth*2 and len(currentRoot.children) > 0 and len(currentRoot.children[0].children) > 0:
	if childrenScored(currentRoot):
		if depth%2 == 0:
			for child in currentRoot.children:
				if child.score is None or child.score <= 0:
					weight = 1
				else:
					weight = child.score
				
				entry = pack('>QHHI', currentRoot.zobrist_hash, child.move, weight, 0)
				global moves
				hash = pack('>Q', currentRoot.zobrist_hash)
				if hash in moves:
					if entry not in moves[hash]:
						moves[hash].append(entry)	
				else:
					moves[hash] = [entry]
				recurseWriteBook(child, depth+1)
		else:
			minChild = min(currentRoot.children, key = lambda child: child.score)
			
			for child in currentRoot.children:	
				recurseWriteBook(child, depth+1)
				
			if minChild == None:
				print(len(currentRoot.children), currentRoot.fen, depth)
			entry = pack('>QHHI', currentRoot.zobrist_hash, minChild.move, 1, 0)		
			hash = pack('>Q', currentRoot.zobrist_hash)
			if hash in moves:
				if entry not in moves[hash]:
					moves[hash].append(entry)	
			else:
				moves[hash] = [entry]			
			
def writeBook():
	recurseWriteBook(root, 0)
	with open(bookFile, "wb") as book:
		for key in sorted(moves):
			for entry in moves[key]:
				book.write(entry)
	print("book saved", len(moves))

def isNew(childA, childrenB):	
	for childB in childrenB:
		if childA.fen == childB.fen:
			return False
	return True
		
transpositions = {}
def collectTranspositions(currentRoot):
	global transpositions	
	if currentRoot.fen in transpositions:
		for child in currentRoot.children:
			if isNew(child, transpositions[currentRoot.fen]):
				transpositions[currentRoot.fen].append(child)
	else:
		transpositions[currentRoot.fen] = currentRoot.children		
	for child in currentRoot.children:
		collectTranspositions(child)

def addTranspositions(currentRoot):
	global transpositions			
	for childT in transpositions[currentRoot.fen]:
		if isNew(childT, currentRoot.children):
			currentRoot.children.append(childT)	
	for child in currentRoot.children:
		addTranspositions(child)

counter = 0
def calcRange(currentRoot, min, max, depth, delta):	
	global engine
	global info_handler
	global counter
	if(currentRoot.ia is None and currentRoot.fen in analysis and analysis[currentRoot.fen][1] >= fixedDepth):
		currentRoot.ia = analysis[currentRoot.fen][0]
		currentRoot.depth = analysis[currentRoot.fen][1]
		currentRoot.add(analysis[currentRoot.fen][2], analysis[currentRoot.fen][3], analysis[currentRoot.fen][4])
		print("rec " + str(currentRoot.ia), end=", ")
	""""if currentRoot.ia is None and currentRoot.public == 1 and delta <= 30:
		print("delta", delta, "fen", currentRoot.fen)
		position = chess.Board(currentRoot.fen)
		engine.position(position)
		res = engine.go(depth=fixedDepth)
		position.push(res[0])
		pmove = convertMovetoPmove(currentRoot.fen, res[0])
		move = currentRoot.add(position.fen(), position.zobrist_hash(), pmove)[1]
		currentRoot.ia = info_handler.info["score"][1].cp
		currentRoot.depth = fixedDepth
		analysis[currentRoot.fen] = (currentRoot.ia, currentRoot.depth, position.fen(), position.zobrist_hash(), move)
		print(depth, fixedDepth, currentRoot.ia)			
		counter += 1"""
	if currentRoot.public <= max:
		if(currentRoot.ia is None or len(currentRoot.children) == 0 or (fixedDepth > currentRoot.depth and abs(currentRoot.ia) < 200)):
			#print(currentRoot.fen)
			position = chess.Board(currentRoot.fen)
			engine.position(position)			
			res = engine.go(depth=fixedDepth+4)
			currentRoot.depth = fixedDepth+4
			position.push(res[0])
			pmove = convertMovetoPmove(currentRoot.fen, res[0])
			move = currentRoot.add(position.fen(), position.zobrist_hash(), pmove)[1]
			currentRoot.ia = info_handler.info["score"][1].cp
			
			analysis[currentRoot.fen] = (currentRoot.ia, currentRoot.depth, position.fen(), position.zobrist_hash(), move)
			print(depth, currentRoot.depth, currentRoot.public, currentRoot.ia)			
			counter += 1
			if counter % 32 == 0:
				print("reached " + str(counter))
			if counter % 500 == 0:				
				save()
	if len(currentRoot.children) > 0 and depth <= ideaDepth*2 and (currentRoot.public >= 3 or (currentRoot.public == 2 and abs(currentRoot.ia) < 200) or (currentRoot.public >= 1 and (delta <= 70 ))):
		for child in currentRoot.children:
			extra = 1
			if child.score is not None and currentRoot.score is not None:
				extra = abs(child.score - currentRoot.score)
			calcRange(child, min, max, depth+1, 1+delta+extra )
	else:
		if(currentRoot.ia is None or len(currentRoot.children) == 0 or (fixedDepth > currentRoot.depth and abs(currentRoot.ia) < 200)):
			print(currentRoot.fen)
			position = chess.Board(currentRoot.fen)
			engine.position(position)
			res = engine.go(depth=fixedDepth)
			position.push(res[0])
			pmove = convertMovetoPmove(currentRoot.fen, res[0])
			move = currentRoot.add(position.fen(), position.zobrist_hash(), pmove)[1]
			currentRoot.ia = info_handler.info["score"][1].cp
			currentRoot.depth = fixedDepth
			analysis[currentRoot.fen] = (currentRoot.ia, currentRoot.depth, position.fen(), position.zobrist_hash(), move)
			print(depth, fixedDepth, currentRoot.public, delta, currentRoot.ia)
			counter += 1
			if counter % 32 == 0:
				print("reached " + str(counter))
			if counter % 500 == 0:				
				save()
		
counter = 0
def getDepth(currentRoot, depth):	
	global engine
	global info_handler
	#if depth < ideaDepth*2 - 1:
	if 'public' not in dir(currentRoot):
		currentRoot.public = 0
	
	if len(currentRoot.children) > 0 and depth <= ideaDepth*2 and currentRoot.public >= 2:
		for child in currentRoot.children:
			getDepth(child, depth+1)
	else:
		if(currentRoot.fen in analysis and analysis[currentRoot.fen][1] >= fixedDepth):
			currentRoot.ia = analysis[currentRoot.fen][0]
			currentRoot.depth = analysis[currentRoot.fen][1]
			currentRoot.add(analysis[currentRoot.fen][2], analysis[currentRoot.fen][3], analysis[currentRoot.fen][4])
			#print("recovered " + str(currentRoot.ia), end=", ")
		if(currentRoot.ia is None or len(currentRoot.children) == 0 or fixedDepth > currentRoot.depth):
			print(currentRoot.fen)
			position = chess.Board(currentRoot.fen)
			engine.position(position)
			res = engine.go(depth=fixedDepth)
			position.push(res[0])
			pmove = convertMovetoPmove(currentRoot.fen, res[0])
			move = currentRoot.add(position.fen(), position.zobrist_hash(), pmove)[1]
			currentRoot.ia = info_handler.info["score"][1].cp
			currentRoot.depth = fixedDepth
			analysis[currentRoot.fen] = (currentRoot.ia, currentRoot.depth, position.fen(), position.zobrist_hash(), move)
			print(depth, currentRoot.ia)
			global counter
			counter += 1
			if counter % 32 == 0:
				print("reached " + str(counter))
			if counter % 500 == 0:				
				save()

engine =  chess.uci.popen_engine(engineLocation)
info_handler = chess.uci.InfoHandler()
engine.uci()	
engine.info_handlers.append(info_handler)
engine.setoption({"Hash": 2048, "Threads": 4, "SyzygyPath": "C:\TB;E:\TB\wdl;E:\TB\dtz"})
signal.signal(signal.SIGINT, Exit_gracefully)	

def calculate():	
	print("started engine analysis")	
	#getDepth(root, 0) #depth in ply
	calcRange(root, 2, 3, 0, 0) #2,18
	
def recurseAddEngineMoves(currentRoot, depth, minDepth, fixedDepth):
	global engine
	global info_handler
	global ideaDepth
	if 'public' not in dir(currentRoot):
		currentRoot.public = False
	if depth >= minDepth*2:
		if(currentRoot.fen in analysis and analysis[currentRoot.fen][1] >= fixedDepth):
			currentRoot.ia = analysis[currentRoot.fen][0]
			currentRoot.depth = analysis[currentRoot.fen][1]
			currentRoot.add(analysis[currentRoot.fen][2], analysis[currentRoot.fen][3], analysis[currentRoot.fen][4])
			#print("recovered " + str(currentRoot.ia))
		if(currentRoot.ia is None or len(currentRoot.children) == 0 or fixedDepth > currentRoot.depth):
			position = chess.Board(currentRoot.fen)
			engine.position(position)
			res = engine.go(depth=fixedDepth)
			position.push(res[0])
			pmove = convertMovetoPmove(currentRoot.fen, res[0])
			move = currentRoot.add(position.fen(), position.zobrist_hash(), pmove)[1]
			currentRoot.ia = info_handler.info["score"][1].cp
			currentRoot.depth = fixedDepth
			analysis[currentRoot.fen] = (currentRoot.ia, currentRoot.depth, position.fen(), position.zobrist_hash(), move)
			print(currentRoot.ia)
			global counter
			counter += 1
			if counter % 32 == 0:
				print("reached " + str(counter))
			if counter % 5000 == 0:				
				save()
	if depth <= ideaDepth*2:
		for child in currentRoot.children:		
			recurseAddEngineMoves(child, depth+1, minDepth, fixedDepth)
	
def addEngineMoves():
	print("started adding moves to book")
	recurseAddEngineMoves(root, 0, 8, fixedDepth)

def childrenAnalyzed(currentRoot):
	if len(currentRoot.children) == 0:
		print("no children")
		return False
	for child in currentRoot.children:
		if child.ia == None:
			return False
	return True
	
def minimax(currentRoot, depth):
	#if depth <= ideaDepth*2 and len(currentRoot.children) > 0 and len(currentRoot.children[0].children) > 0 and currentRoot.public == True:
	if (depth < ideaDepth*2 and len(currentRoot.children) > 0 and currentRoot.public > 3) or childrenAnalyzed(currentRoot):
		for child in currentRoot.children:
			minimax(child, depth+1)
	else:
		if currentRoot.ia is None:
			print("None", depth, len(currentRoot.children), currentRoot.public, childrenAnalyzed(currentRoot), currentRoot.fen)
		if depth%2 == 0:
			currentRoot.score = currentRoot.ia
		else:
			currentRoot.score = -currentRoot.ia
		return currentRoot.score
	
	measure = min if depth % 2 else max
	currentRoot.score = measure(c.score for c in currentRoot.children)
	return currentRoot.score
	
for file in glob.glob(r"E:\pgn\*.pgn"):	
	print(file)
	createTree(file)

calculate()
#save()

collectTranspositions(root)
print("len transpositions", len(transpositions))
addTranspositions(root)
print("recalculate")
calculate()
save()
print("starting minimax")
minimax(root, 0)
for child in root.children:
	print (child.fen, child.score)
print("writing book.bin")
writeBook()

fixedDepth=27
calcRange(root, 2, 255, 0, 0)
#save()
collectTranspositions(root)
print("len transpositions", len(transpositions))
addTranspositions(root)
print("recalculate")
calculate()
minimax(root, 0)
for child in root.children:
	print (child.fen, child.score)
writeBook()
save()
