from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.static import serve


def index(request):
    index_path: Path = settings.FRONTEND_DIST / "index.html"
    if not index_path.is_file():
        raise Http404(
            "frontend/dist/index.html not found -- run `npm run build` in steerweb/frontend first."
        )
    return HttpResponse(index_path.read_bytes(), content_type="text/html")


def frontend_assets(request, path):
    return serve(request, path, document_root=settings.FRONTEND_DIST / "assets")
