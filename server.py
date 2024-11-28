import logging
from aiohttp import web
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('gpu-monitor')

async def handle_static(request):
    file_path = request.path.strip('/')
    if not file_path:
        file_path = 'gpu-stats.html'
    if os.path.exists(file_path):
        return web.FileResponse(file_path)
    return web.Response(status=404)

app = web.Application()
app.router.add_get('/{tail:.*}', handle_static)

if __name__ == '__main__':
    logger.info("========================================")
    logger.info("Starting NVIDIA GPU Monitor")
    logger.info("https://github.com/bigsk1/gpu-monitor")
    logger.info("----------------------------------------")
    logger.info("Server running on: http://localhost:8081")
    logger.info("========================================")
    
    web.run_app(app, port=8081, access_log=None)