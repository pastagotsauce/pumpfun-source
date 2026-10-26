# Original instruction bytes [0x59408, 0x59428)
   59408: bf 39 00 00 00 00 00 00      	mov64 r9, r3
   59410: bf 27 00 00 00 00 00 00      	mov64 r7, r2
   59418: bf 16 00 00 00 00 00 00      	mov64 r6, r1
   59420: 79 78 08 00 00 00 00 00      	ldxdw r8, [r7 + 0x8]
# Original instruction bytes [0x59c08, 0x59c60)
   59c08: 79 82 10 00 00 00 00 00      	ldxdw r2, [r8 + 0x10]
   59c10: 07 02 00 00 08 00 00 00      	add64 r2, 0x8
   59c18: bf a1 00 00 00 00 00 00      	mov64 r1, r10
   59c20: 07 01 00 00 e8 fd ff ff      	add64 r1, -0x218
   59c28: bf 93 00 00 00 00 00 00      	mov64 r3, r9
   59c30: 85 10 00 00 9e 26 00 00      	call 0x269e
   59c38: 79 a1 e8 fd 00 00 00 00      	ldxdw r1, [r10 - 0x218]
   59c40: 15 01 01 00 02 00 00 00      	jeq r1, 0x2, +0x1 <.text+0x59b30>
   59c48: 05 00 37 00 00 00 00 00      	ja +0x37 <.text+0x59ce8>
   59c50: 79 a6 f0 fd 00 00 00 00      	ldxdw r6, [r10 - 0x210]
   59c58: 15 06 39 00 00 00 00 00      	jeq r6, 0x0, +0x39 <.text+0x59d08>
# Original instruction bytes [0x59e08, 0x59ef8)
   59e08: 79 a2 f0 fd 00 00 00 00      	ldxdw r2, [r10 - 0x210]
   59e10: 7b 26 08 00 00 00 00 00      	stxdw [r6 + 0x8], r2
   59e18: 7b 16 00 00 00 00 00 00      	stxdw [r6 + 0x0], r1
   59e20: 95 00 00 00 00 00 00 00      	exit
   59e28: 18 01 00 00 80 25 12 00 00 00 00 00 00 00 00 00      	lddw r1, 0x122580
   59e38: 7b 1a e8 fd 00 00 00 00      	stxdw [r10 - 0x218], r1
   59e40: bf a1 00 00 00 00 00 00      	mov64 r1, r10
   59e48: 07 01 00 00 98 ff ff ff      	add64 r1, -0x68
   59e50: 7b 1a f8 fd 00 00 00 00      	stxdw [r10 - 0x208], r1
   59e58: 18 01 00 00 20 93 11 00 00 00 00 00 00 00 00 00      	lddw r1, 0x119320
   59e68: 7b 1a a0 ff 00 00 00 00      	stxdw [r10 - 0x60], r1
   59e70: bf a1 00 00 00 00 00 00      	mov64 r1, r10
   59e78: 07 01 00 00 d8 ff ff ff      	add64 r1, -0x28
   59e80: 7b 1a 98 ff 00 00 00 00      	stxdw [r10 - 0x68], r1
   59e88: 73 9a d8 ff 00 00 00 00      	stxb [r10 - 0x28], r9
   59e90: 7a 0a 08 fe 00 00 00 00      	stdw [r10 - 0x1f8], 0x0
   59e98: 7a 0a f0 fd 01 00 00 00      	stdw [r10 - 0x210], 0x1
   59ea0: 7a 0a 00 fe 01 00 00 00      	stdw [r10 - 0x200], 0x1
   59ea8: bf a1 00 00 00 00 00 00      	mov64 r1, r10
   59eb0: 07 01 00 00 30 ff ff ff      	add64 r1, -0xd0
   59eb8: bf a2 00 00 00 00 00 00      	mov64 r2, r10
   59ec0: 07 02 00 00 e8 fd ff ff      	add64 r2, -0x218
   59ec8: 85 10 00 00 1b 62 ff ff      	call -0x9de5
   59ed0: 79 a1 38 ff 00 00 00 00      	ldxdw r1, [r10 - 0xc8]
   59ed8: 79 a2 40 ff 00 00 00 00      	ldxdw r2, [r10 - 0xc0]
   59ee0: 85 10 00 00 ff ff ff ff      	call -0x1
   59ee8: b7 01 00 00 02 00 00 00      	mov64 r1, 0x2
   59ef0: 05 00 56 ff 00 00 00 00      	ja -0xaa <.text+0x59888>
# Original instruction bytes [0x6d128, 0x6d208)
   6d128: bf 16 00 00 00 00 00 00      	mov64 r6, r1
   6d130: b7 01 00 00 08 01 00 00      	mov64 r1, 0x108
   6d138: 55 03 01 00 00 00 00 00      	jne r3, 0x0, +0x1 <.text+0x6d028>
   6d140: b7 01 00 00 00 01 00 00      	mov64 r1, 0x100
   6d148: bf 23 00 00 00 00 00 00      	mov64 r3, r2
   6d150: 0f 13 00 00 00 00 00 00      	add64 r3, r1
   6d158: 79 31 00 00 00 00 00 00      	ldxdw r1, [r3 + 0x0]
   6d160: 7a 03 00 00 00 00 00 00      	stdw [r3 + 0x0], 0x0
   6d168: 79 24 e0 00 00 00 00 00      	ldxdw r4, [r2 + 0xe0]
   6d170: bf 43 00 00 00 00 00 00      	mov64 r3, r4
   6d178: 0f 13 00 00 00 00 00 00      	add64 r3, r1
   6d180: b7 00 00 00 01 00 00 00      	mov64 r0, 0x1
   6d188: ad 43 01 00 00 00 00 00      	jlt r3, r4, +0x1 <.text+0x6d078>
   6d190: b7 00 00 00 00 00 00 00      	mov64 r0, 0x0
   6d198: 79 25 e8 00 00 00 00 00      	ldxdw r5, [r2 + 0xe8]
   6d1a0: bf 54 00 00 00 00 00 00      	mov64 r4, r5
   6d1a8: 0f 04 00 00 00 00 00 00      	add64 r4, r0
   6d1b0: bf 50 00 00 00 00 00 00      	mov64 r0, r5
   6d1b8: af 40 00 00 00 00 00 00      	xor64 r0, r4
   6d1c0: a7 05 00 00 ff ff ff ff      	xor64 r5, -0x1
   6d1c8: 5f 05 00 00 00 00 00 00      	and64 r5, r0
   6d1d0: c5 05 00 00 00 00 00 00      	jslt r5, 0x0, +0x0 <.text+0x6d0b8>
   6d1d8: c5 05 05 00 00 00 00 00      	jslt r5, 0x0, +0x5 <.text+0x6d0e8>
   6d1e0: 7b 32 e0 00 00 00 00 00      	stxdw [r2 + 0xe0], r3
   6d1e8: 7b 42 e8 00 00 00 00 00      	stxdw [r2 + 0xe8], r4
   6d1f0: 7b 16 08 00 00 00 00 00      	stxdw [r6 + 0x8], r1
   6d1f8: 7a 06 00 00 02 00 00 00      	stdw [r6 + 0x0], 0x2
   6d200: 05 00 3f 00 00 00 00 00      	ja +0x3f <.text+0x6d2e0>
