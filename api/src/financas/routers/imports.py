from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from pydantic import StringConstraints

from financas.deps import ContextDep, CurrentUser, SessionDep
from financas.importers import StatementError, parse_statement
from financas.schemas import ImportOut
from financas.services.imports import import_rows, list_imports

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024

AccountName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_statement(
    file: UploadFile,
    account_name: Annotated[AccountName, Form()],
    user: CurrentUser,
    session: SessionDep,
    context: ContextDep,
) -> ImportOut:
    """Import an OFX or CSV statement. The format is detected from the content."""
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "O arquivo passa de 2 MB.")
    try:
        statement = parse_statement(content)
    except StatementError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None

    batch = import_rows(
        session,
        user_id=user.id,
        account_name=account_name,
        filename=file.filename or "extrato",
        file_format=statement.file_format,
        rows=statement.rows,
        categorizer=context.categorizer,
        pricing=context.pricing,
    )
    return ImportOut.model_validate(batch)


@router.get("")
def import_history(user: CurrentUser, session: SessionDep) -> list[ImportOut]:
    return [ImportOut.model_validate(batch) for batch in list_imports(session, user.id)]
