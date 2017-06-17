import re

with open("XPS_Q8_drivers.py") as f:
    full = f.readlines()
    print(len(full))
    i = 0
    prob = re.compile(r"XPS\.__usedSockets\[socketId\]")
    d = []
    for i, line in enumerate(full):
        if prob.search(line) is not None:
            d.append(i)
    for i in d[::-1]:
        del full[i:i+3]
    with open("XPS_Q8_drivers2.py", 'w') as g:
        g.writelines(full)
