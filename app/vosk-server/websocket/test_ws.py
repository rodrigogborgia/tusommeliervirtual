import asyncio, websockets, json

async def test_vosk():
    uri = "ws://localhost:2700"
    async with websockets.connect(uri) as ws:
        # Config inicial
        await ws.send(json.dumps({"config": {"sample_rate": 16000}}))

        # Enviar audio crudo en chunks
        with open("/opt/tusommeliervirtual.com/hola.raw", "rb") as f:
            while True:
                data = f.read(4000)
                if not data:
                    break
                await ws.send(data)

        # Señalar fin
        await ws.send(b'{"eof":1}')

        # Recibir resultados hasta que el server cierre
        try:
            async for msg in ws:
                print(json.loads(msg))
        except websockets.exceptions.ConnectionClosedOK:
            print("Conexión cerrada limpiamente por el servidor")

asyncio.run(test_vosk())
