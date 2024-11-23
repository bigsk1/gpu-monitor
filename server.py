from aiohttp import web
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    logger.info("Starting GPU Monitor Server")
    logger.info("Serving on port: 8081")
    logger.info("Dashboard available at: http://localhost:8081")
    web.run_app(app, port=8081, access_log=None)