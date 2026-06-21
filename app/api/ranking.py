from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import settings
from app.core.efficiency import (
    aggregate_cabinet_savings,
    format_saving_ranking_table,
    log_saving_ranking,
)
from app.database import get_db

router = APIRouter(prefix="/savings-ranking", tags=["电费节省排行"])


def _build_ranking_response(db: Session, top_n: int, output_file: Optional[str] = None):
    records = crud.list_all_efficiency_with_tests(db, limit=100000)
    ranked = aggregate_cabinet_savings(records)

    log_saving_ranking(ranked, top_n=top_n, output_file=output_file)

    display = ranked[:top_n]
    ranking_data = []
    for idx, cab in enumerate(display, 1):
        ranking_data.append(
            schemas.CabinetSavingRank(
                rank=idx,
                cabinet_id=cab.cabinet_id,
                total_tests=cab.total_tests,
                total_recovered_energy_kwh=cab.total_recovered_kwh,
                total_cost_saved_yuan=cab.total_saved_yuan,
            )
        )

    return schemas.SavingRankResponse(
        generated_at=datetime.utcnow(),
        total_cabinets=len(ranked),
        top_n=top_n,
        ranking=ranking_data,
        report_file=output_file or settings.saving_report_log_file,
    )


@router.post(
    "/generate",
    response_model=schemas.SavingRankResponse,
    status_code=status.HTTP_201_CREATED,
    summary="统计并生成电费节省TOP N排行榜（自动输出到日志和文件）",
)
def generate_ranking(
    top_n: int = Query(settings.top_saving_rank_count, ge=1, le=20, description="显示前N名"),
    output_file: Optional[str] = Query(None, description="输出报告文件路径，默认使用配置"),
    db: Session = Depends(get_db),
):
    return _build_ranking_response(db, top_n=top_n, output_file=output_file)


@router.get(
    "",
    response_model=schemas.SavingRankResponse,
    summary="查询电费节省排行榜（自动触发统计）",
)
def get_ranking(
    top_n: int = Query(settings.top_saving_rank_count, ge=1, le=20, description="显示前N名"),
    db: Session = Depends(get_db),
):
    return _build_ranking_response(db, top_n=top_n)


@router.get(
    "/report",
    summary="获取文本格式的排行报告",
)
def get_ranking_report(
    top_n: int = Query(settings.top_saving_rank_count, ge=1, le=20, description="显示前N名"),
    db: Session = Depends(get_db),
):
    records = crud.list_all_efficiency_with_tests(db, limit=100000)
    ranked = aggregate_cabinet_savings(records)
    table = format_saving_ranking_table(ranked, top_n=top_n)
    return Response(content=table, media_type="text/plain; charset=utf-8")


@router.get(
    "/print-to-log",
    summary="手动触发将排行榜打印到日志和文件",
)
def print_ranking_to_log(
    top_n: int = Query(settings.top_saving_rank_count, ge=1, le=20),
    db: Session = Depends(get_db),
):
    records = crud.list_all_efficiency_with_tests(db, limit=100000)
    ranked = aggregate_cabinet_savings(records)
    output = log_saving_ranking(ranked, top_n=top_n)
    return {
        "status": "ok",
        "printed_lines": output.count("\n") + 1,
        "top_n": top_n,
        "output_file": settings.saving_report_log_file,
    }
