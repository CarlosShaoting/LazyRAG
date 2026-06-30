from fastapi import APIRouter

router = APIRouter()


@router.get('/health', summary='Health check')
@router.get('/api/health', summary='Health check (API path)')
async def health():
    return {'status': 'ok'}
