from fastapi import APIRouter

router = APIRouter(prefix='/sources', tags=['sources'])


@router.get('/health')
def sources_health() -> dict:
    return {'status': 'ok'}
