"""
交易监控 Dashboard - Flask Web 应用

启动方式: python main.py dashboard
"""
import json
from flask import Flask, render_template, jsonify, request
from loguru import logger

from monitor.trade_store import TradeStore


def create_app(trade_store: TradeStore = None) -> Flask:
    """创建 Flask 应用"""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    store = trade_store or TradeStore()

    # ------------------------------------------------------------------
    #  页面路由
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        """总览页"""
        import time
        return render_template("index.html", v=int(time.time()))

    @app.route("/trades")
    def trades_page():
        """交易明细页"""
        return render_template("trades.html")

    @app.route("/pnl")
    def pnl_page():
        """盈亏统计页"""
        return render_template("pnl.html")

    # ------------------------------------------------------------------
    #  API 路由
    # ------------------------------------------------------------------

    @app.route("/api/summary")
    def api_summary():
        """统计摘要"""
        mode = request.args.get("mode", "paper")
        start = request.args.get("start")
        end = request.args.get("end")
        return jsonify(store.get_summary(mode, start, end))

    @app.route("/api/equity")
    def api_equity():
        """资金曲线"""
        mode = request.args.get("mode", "paper")
        start = request.args.get("start")
        end = request.args.get("end")
        return jsonify(store.get_equity_curve(mode, start, end))

    @app.route("/api/trades")
    def api_trades():
        """交易记录"""
        mode = request.args.get("mode", "paper")
        etf_code = request.args.get("etf_code")
        start = request.args.get("start")
        end = request.args.get("end")
        limit = int(request.args.get("limit", 500))
        return jsonify(store.get_trades(mode, etf_code, start, end, limit))

    @app.route("/api/pnl/daily")
    def api_daily_pnl():
        """每日盈亏"""
        mode = request.args.get("mode", "paper")
        start = request.args.get("start")
        end = request.args.get("end")
        return jsonify(store.get_daily_pnl(mode, start, end))

    @app.route("/api/pnl/weekly")
    def api_weekly_pnl():
        """每周盈亏"""
        mode = request.args.get("mode", "paper")
        return jsonify(store.get_weekly_pnl(mode))

    @app.route("/api/pnl/monthly")
    def api_monthly_pnl():
        """每月盈亏"""
        mode = request.args.get("mode", "paper")
        return jsonify(store.get_monthly_pnl(mode))

    @app.route("/api/symbol_stats")
    def api_symbol_stats():
        """分标的盈亏统计"""
        mode = request.args.get("mode", "paper")
        start = request.args.get("start")
        end = request.args.get("end")
        return jsonify(store.get_symbol_stats(mode, start, end))

    @app.route("/api/config")
    def api_config():
        """输出当前系统配置（标的列表等）"""
        from config.etf_settings import ACTIVE_ETFS, ETF_UNIVERSE
        etfs = []
        for code in ACTIVE_ETFS:
            info = ETF_UNIVERSE.get(code, {})
            etfs.append({
                "code": code,
                "name": info.get("name", "未知"),
            })
        return jsonify({"etfs": etfs})

    @app.route("/api/snapshots")
    def api_snapshots():
        """实时行情快照"""
        mode = request.args.get("mode", "paper")
        etf_code = request.args.get("etf_code")
        limit = int(request.args.get("limit", 3000))
        if not etf_code:
            return jsonify([])
        return jsonify(store.get_recent_snapshots(mode, etf_code, limit))

    return app


def run_dashboard(port: int = 5000):
    """启动 Dashboard"""
    logger.info(f"启动交易监控 Dashboard: http://localhost:{port}")
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=False)
