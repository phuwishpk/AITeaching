"""หน้า "กฎทั้งหมด": ครูและ Admin เห็นกฎชุดเดียวกัน (นักเรียนไม่เห็น เพราะรู้เกณฑ์แล้วอาจใช้เลี่ยงกฎได้)"""

from fastapi import APIRouter, Depends

from .. import rules
from .deps import require

router = APIRouter(prefix="/api", tags=["rules"])


@router.get("/rules")
def all_rules(auth: dict = Depends(require("teacher", "admin"))):
    return rules.build()
