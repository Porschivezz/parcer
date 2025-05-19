﻿from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Body, Request, Depends, HTTPException, Response, status  # noqa
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import ORJSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

import crud, models, schemas  # noqa
from api import deps  # noqa
from core import security  # noqa
from core.config import settings  # noqa
from core.security import get_password_hash  # noqa
from core.utils import (  # noqa
    generate_password_reset_token,  # noqa
    verify_password_reset_token,  # noqa
)

router = APIRouter()


def get_tokens(sub):
    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(
        minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)

    response = ORJSONResponse(content={
        'access_token': security.create_access_token(
            sub, expires_delta=access_token_expires
        ),
        'token_type': 'bearer',
    })
    response.set_cookie(
        key="refresh-token",
        value=security.create_refresh_token(
            sub, expires_delta=refresh_token_expires
        )
    )
    return response


@router.post('/access-token', response_model=schemas.Token)
async def login_access_token(
    db: AsyncSession = Depends(deps.get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    '''
    OAuth2 compatible token login, get an access token for future requests
    '''
    user = await crud.user.authenticate(
        db, login=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Incorrect login or password')
    elif not crud.user.is_active(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Inactive user')
    return get_tokens(user.id)


@router.post('/refresh-token', response_model=schemas.Token)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    '''
    Refresh token
    '''
    token = request.cookies.get('refresh-token')

    user_id = int(verify_password_reset_token(token))
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Invalid token')
    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='The user with this ID does not exist in the system.',
        )
    elif not crud.user.is_active(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Inactive user')
    return get_tokens(user.id)


@router.post('/test-token', response_model=schemas.User)
async def test_token(
    current_user: models.User = Depends(deps.get_current_user)
) -> Any:
    '''
    Test access token
    '''
    return current_user