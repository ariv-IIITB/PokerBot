import os
d=os.path.dirname(os.path.abspath(__file__))
s=open(d+'/bot_src.py').read().replace('@@DATA@@',open(d+'/pre3_data.txt').read())
open(d+'/bot.py','w').write(s)
