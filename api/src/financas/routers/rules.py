from fastapi import APIRouter, HTTPException, status

from financas.deps import CurrentUser, SessionDep
from financas.schemas import RuleCreated, RuleIn, RuleOut
from financas.services.transactions import delete_rule, list_rules, save_rule
from financas.text import normalize

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("")
def user_rules(user: CurrentUser, session: SessionDep) -> list[RuleOut]:
    return [RuleOut.model_validate(rule) for rule in list_rules(session, user.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, user: CurrentUser, session: SessionDep) -> RuleCreated:
    """Create a rule and apply it to existing transactions (manual choices are kept)."""
    if len(normalize(body.pattern)) < 3:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "O padrão precisa de pelo menos 3 letras ou números.",
        )
    rule, applied = save_rule(session, user.id, body.pattern, body.category)
    return RuleCreated(rule=RuleOut.model_validate(rule), applied=applied)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_rule(rule_id: int, user: CurrentUser, session: SessionDep) -> None:
    if not delete_rule(session, user.id, rule_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra não encontrada.")
