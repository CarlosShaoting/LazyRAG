from lazyllm import TrainableModule
import time
emb = TrainableModule('siglip')
emb.start()

while True:
    time.sleep(60)