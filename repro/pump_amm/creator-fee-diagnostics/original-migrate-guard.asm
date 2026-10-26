# Original bytes [0x23e40,0x23f30)
   23e40: bf 16 00 00 00 00 00 00      	mov64 r6, r1
   23e48: 79 27 08 00 00 00 00 00      	ldxdw r7, [r2 + 0x8]
   23e50: 71 71 e6 01 00 00 00 00      	ldxb r1, [r7 + 0x1e6]
   23e58: 55 01 1b 00 00 00 00 00      	jne r1, 0x0, +0x1b <.text+0x23e18>
   23e60: 79 71 d8 01 00 00 00 00      	ldxdw r1, [r7 + 0x1d8]
   23e68: 15 01 73 00 00 00 00 00      	jeq r1, 0x0, +0x73 <.text+0x240e8>
   23e70: bf a1 00 00 00 00 00 00      	mov64 r1, r10
   23e78: 07 01 00 00 d8 ff ff ff      	add64 r1, -0x28
   23e80: 18 02 00 00 bc c0 11 00 00 00 00 00 00 00 00 00      	lddw r2, 0x11c0bc
   23e90: 85 10 00 00 ac a2 00 00      	call 0xa2ac
   23e98: 7a 0a a8 ff 00 00 00 00      	stdw [r10 - 0x58], 0x0
   23ea0: 7a 0a a0 ff 01 00 00 00      	stdw [r10 - 0x60], 0x1
   23ea8: 7a 0a 98 ff 00 00 00 00      	stdw [r10 - 0x68], 0x0
   23eb0: 18 01 00 00 e0 21 12 00 00 00 00 00 00 00 00 00      	lddw r1, 0x1221e0
   23ec0: 7b 1a 58 ff 00 00 00 00      	stxdw [r10 - 0xa8], r1
   23ec8: bf a1 00 00 00 00 00 00      	mov64 r1, r10
   23ed0: 07 01 00 00 98 ff ff ff      	add64 r1, -0x68
   23ed8: 7b 1a 50 ff 00 00 00 00      	stxdw [r10 - 0xb0], r1
   23ee0: 72 0a 68 ff 03 00 00 00      	stb [r10 - 0x98], 0x3
   23ee8: 7a 0a 60 ff 20 00 00 00      	stdw [r10 - 0xa0], 0x20
   23ef0: 7a 0a 40 ff 00 00 00 00      	stdw [r10 - 0xc0], 0x0
   23ef8: 7a 0a 30 ff 00 00 00 00      	stdw [r10 - 0xd0], 0x0
   23f00: bf a2 00 00 00 00 00 00      	mov64 r2, r10
   23f08: 07 02 00 00 30 ff ff ff      	add64 r2, -0xd0
   23f10: 18 01 00 00 bc c0 11 00 00 00 00 00 00 00 00 00      	lddw r1, 0x11c0bc
   23f20: 85 10 00 00 8f ad 00 00      	call 0xad8f
   23f28: 15 00 3f 00 00 00 00 00      	jeq r0, 0x0, +0x3f <.text+0x24008>
# Original bytes [0x24128,0x24208)
   24128: 79 a1 a8 ff 00 00 00 00      	ldxdw r1, [r10 - 0x58]
   24130: 7b 1a d8 fe 00 00 00 00      	stxdw [r10 - 0x128], r1
   24138: 79 a1 a0 ff 00 00 00 00      	ldxdw r1, [r10 - 0x60]
   24140: 7b 1a d0 fe 00 00 00 00      	stxdw [r10 - 0x130], r1
   24148: 79 a1 98 ff 00 00 00 00      	ldxdw r1, [r10 - 0x68]
   24150: 7b 1a c8 fe 00 00 00 00      	stxdw [r10 - 0x138], r1
   24158: 79 a1 d8 ff 00 00 00 00      	ldxdw r1, [r10 - 0x28]
   24160: 7b 1a b0 fe 00 00 00 00      	stxdw [r10 - 0x150], r1
   24168: 79 a1 e0 ff 00 00 00 00      	ldxdw r1, [r10 - 0x20]
   24170: 7b 1a b8 fe 00 00 00 00      	stxdw [r10 - 0x148], r1
   24178: 79 a1 e8 ff 00 00 00 00      	ldxdw r1, [r10 - 0x18]
   24180: 7b 1a c0 fe 00 00 00 00      	stxdw [r10 - 0x140], r1
   24188: 18 01 00 00 75 c8 11 00 00 00 00 00 00 00 00 00      	lddw r1, 0x11c875
   24198: 7b 1a 98 fe 00 00 00 00      	stxdw [r10 - 0x168], r1
   241a0: 62 0a 28 ff c1 17 00 00      	stw [r10 - 0xd8], 0x17c1
   241a8: 72 0a e0 fe 02 00 00 00      	stb [r10 - 0x120], 0x2
   241b0: 62 0a a8 fe 3b 00 00 00      	stw [r10 - 0x158], 0x3b
   241b8: 7a 0a a0 fe 4c 00 00 00      	stdw [r10 - 0x160], 0x4c
   241c0: 7a 0a 90 fe 00 00 00 00      	stdw [r10 - 0x170], 0x0
   241c8: bf a1 00 00 00 00 00 00      	mov64 r1, r10
   241d0: 07 01 00 00 50 fe ff ff      	add64 r1, -0x1b0
   241d8: bf a2 00 00 00 00 00 00      	mov64 r2, r10
   241e0: 07 02 00 00 90 fe ff ff      	add64 r2, -0x170
   241e8: 85 10 00 00 b9 bd 01 00      	call 0x1bdb9
   241f0: 79 a1 58 fe 00 00 00 00      	ldxdw r1, [r10 - 0x1a8]
   241f8: 79 a2 50 fe 00 00 00 00      	ldxdw r2, [r10 - 0x1b0]
   24200: 05 00 b5 01 00 00 00 00      	ja +0x1b5 <.text+0x24e90>
