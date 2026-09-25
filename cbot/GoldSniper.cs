// =====================================================================
//  GOLD SNIPER - cBot per cTrader
//  Tregton VETEM XAUUSD ne M15.
//  Kap majat (tops) dhe fundet (bottoms): cmimi fshin maksimumin/minimumin
//  e fundit (liquidity sweep) dhe refuzohet me nje qiri me bisht te gjate
//  ose me nje qiri konfirmues ne drejtim te kundert.
//
//  SELL ne maje  : qiri ben high te ri > high-et e N qirinjve te meparshem,
//                  pastaj refuzohet (bisht lart / mbyllje poshte).
//  BUY ne fund   : qiri ben low te ri < low-et e N qirinjve te meparshem,
//                  pastaj refuzohet (bisht poshte / mbyllje lart).
//  SL            : pertej majes/fundit + buffer (ATR).
//  TP            : Risk:Reward (p.sh. 1:2), me break-even opsional.
// =====================================================================
using System;
using System.Linq;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None, AddIndicators = true)]
    public class GoldSniper : Robot
    {
        // ---------------- Menaxhimi i rrezikut ----------------
        [Parameter("Label", DefaultValue = "GoldSniper", Group = "Rreziku")]
        public string BotLabel { get; set; }

        [Parameter("Perdor lot fiks", DefaultValue = false, Group = "Rreziku")]
        public bool UseFixedLots { get; set; }

        [Parameter("Lot fiks", DefaultValue = 0.01, MinValue = 0.01, Step = 0.01, Group = "Rreziku")]
        public double FixedLots { get; set; }

        [Parameter("Rreziku % per trade", DefaultValue = 0.5, MinValue = 0.1, MaxValue = 10, Step = 0.1, Group = "Rreziku")]
        public double RiskPercent { get; set; }

        [Parameter("Perdor volumin min nese rreziku eshte i vogel", DefaultValue = true, Group = "Rreziku")]
        public bool AllowMinVolume { get; set; }

        [Parameter("Risk:Reward (TP)", DefaultValue = 3.0, MinValue = 0.5, MaxValue = 10, Step = 0.1, Group = "Rreziku")]
        public double RewardRatio { get; set; }

        [Parameter("Break-even pas R (0 = joaktiv)", DefaultValue = 1.0, MinValue = 0, MaxValue = 5, Step = 0.1, Group = "Rreziku")]
        public double BreakEvenAtR { get; set; }

        [Parameter("Humbja max ditore %", DefaultValue = 3.0, MinValue = 0.5, MaxValue = 50, Step = 0.5, Group = "Rreziku")]
        public double MaxDailyLossPercent { get; set; }

        [Parameter("Trade max ne dite", DefaultValue = 4, MinValue = 1, MaxValue = 50, Group = "Rreziku")]
        public int MaxTradesPerDay { get; set; }

        // ---------------- Strategjia (majat / fundet) ----------------
        [Parameter("Qirinj per maje/fund (lookback)", DefaultValue = 32, MinValue = 5, MaxValue = 200, Group = "Strategjia")]
        public int SwingLookback { get; set; }

        [Parameter("Levizja min para majes (x ATR)", DefaultValue = 3.0, MinValue = 0, MaxValue = 20, Step = 0.1, Group = "Strategjia")]
        public double MinLegAtr { get; set; }

        [Parameter("Bishti min (% e qirit)", DefaultValue = 40, MinValue = 0, MaxValue = 90, Group = "Strategjia")]
        public double MinWickPercent { get; set; }

        [Parameter("Mbyllja e refuzimit (% e qirit)", DefaultValue = 50, MinValue = 0, MaxValue = 100, Group = "Strategjia")]
        public double MinClosePercent { get; set; }

        [Parameter("Perdor filtrin RSI", DefaultValue = true, Group = "Strategjia")]
        public bool UseRsiFilter { get; set; }

        [Parameter("RSI periudha", DefaultValue = 14, MinValue = 2, Group = "Strategjia")]
        public int RsiPeriod { get; set; }

        [Parameter("RSI mbiblerje (SELL)", DefaultValue = 65, MinValue = 50, MaxValue = 95, Group = "Strategjia")]
        public double RsiOverbought { get; set; }

        [Parameter("RSI mbishitje (BUY)", DefaultValue = 35, MinValue = 5, MaxValue = 50, Group = "Strategjia")]
        public double RsiOversold { get; set; }

        [Parameter("ATR periudha", DefaultValue = 14, MinValue = 2, Group = "Strategjia")]
        public int AtrPeriod { get; set; }

        [Parameter("SL buffer (x ATR)", DefaultValue = 0.3, MinValue = 0, MaxValue = 5, Step = 0.05, Group = "Strategjia")]
        public double SlBufferAtr { get; set; }

        [Parameter("SL min ($ cmim)", DefaultValue = 3.0, MinValue = 0.1, Group = "Strategjia")]
        public double MinSlPrice { get; set; }

        [Parameter("SL max ($ cmim)", DefaultValue = 25.0, MinValue = 1, Group = "Strategjia")]
        public double MaxSlPrice { get; set; }

        // ---------------- Filtrat ----------------
        [Parameter("Ora e fillimit (UTC)", DefaultValue = 1, MinValue = 0, MaxValue = 23, Group = "Filtrat")]
        public int StartHourUtc { get; set; }

        [Parameter("Ora e mbarimit (UTC)", DefaultValue = 20, MinValue = 0, MaxValue = 24, Group = "Filtrat")]
        public int EndHourUtc { get; set; }

        [Parameter("Spread max (pips)", DefaultValue = 50, MinValue = 1, Group = "Filtrat")]
        public double MaxSpreadPips { get; set; }

        [Parameter("Pritja pas trade-it (qirinj)", DefaultValue = 4, MinValue = 0, Group = "Filtrat")]
        public int CooldownBars { get; set; }

        [Parameter("Vizato zonat ne grafik", DefaultValue = true, Group = "Filtrat")]
        public bool DrawZones { get; set; }

        private AverageTrueRange _atr;
        private RelativeStrengthIndex _rsi;

        private DateTime _currentDay;
        private double _dayStartBalance;
        private int _tradesToday;
        private bool _dailyLimitHit;
        private int _lastSignalBarIndex = -1000;

        protected override void OnStart()
        {
            if (!IsGoldSymbol(SymbolName))
            {
                Print("GABIM: Ky bot tregton vetem XAUUSD. Simboli aktual: {0}. Boti ndalon.", SymbolName);
                Stop();
                return;
            }

            if (TimeFrame != TimeFrame.Minute15)
            {
                Print("GABIM: Ky bot punon vetem ne M15. Timeframe aktual: {0}. Boti ndalon.", TimeFrame);
                Stop();
                return;
            }

            _atr = Indicators.AverageTrueRange(AtrPeriod, MovingAverageType.Exponential);
            _rsi = Indicators.RelativeStrengthIndex(Bars.ClosePrices, RsiPeriod);

            ResetDay(Server.Time.Date);
            Positions.Closed += OnPositionClosed;

            Print("Gold Sniper filloi | {0} M15 | Llogaria: {1} | Balanca: {2} {3}",
                SymbolName, Account.Number, Account.Balance, Account.Asset.Name);
        }

        protected override void OnStop()
        {
            Positions.Closed -= OnPositionClosed;
        }

        protected override void OnTick()
        {
            ManageBreakEven();
            CheckDailyLoss();
        }

        // Thirret kur hapet nje qiri i ri -> analizojme qirinjte e mbyllur
        protected override void OnBar()
        {
            if (Server.Time.Date != _currentDay)
                ResetDay(Server.Time.Date);

            int i = Bars.Count - 2; // qiri i fundit i mbyllur
            if (i < SwingLookback + 3)
                return;

            TradeType? signal = DetectSignal(i, out double extremePrice, out int extremeIndex);
            if (signal == null)
                return;

            if (DrawZones)
                DrawZone(signal.Value, extremeIndex, extremePrice);

            if (!CanTrade(i))
                return;

            OpenTrade(signal.Value, extremePrice, i);
        }

        // ================================================================
        //  Zbulimi i majes / fundit
        // ================================================================
        private TradeType? DetectSignal(int i, out double extremePrice, out int extremeIndex)
        {
            extremePrice = 0;
            extremeIndex = -1;
            double atr = _atr.Result[i];
            if (double.IsNaN(atr) || atr <= 0)
                return null;

            // Qiri ekstrem mund te jete qiri i fundit (i) ose ai para tij (i-1, konfirmuar nga i)
            for (int k = i; k >= i - 1; k--)
            {
                // ------ MAJE -> SELL ------
                double priorHigh = Highest(k - SwingLookback, k - 1);
                double highK = Bars.HighPrices[k];
                if (highK > priorHigh && highK >= Bars.HighPrices[i] && highK >= Bars.HighPrices[i - 1])
                {
                    double legLow = Lowest(k - SwingLookback, k);
                    bool bigMove = highK - legLow >= MinLegAtr * atr;
                    bool rsiOk = !UseRsiFilter || Math.Max(_rsi.Result[k], _rsi.Result[k - 1]) >= RsiOverbought;
                    bool rejected = (k == i) ? IsBearishRejection(k) : IsBearishConfirmation(i, k);

                    if (bigMove && rsiOk && rejected)
                    {
                        extremePrice = highK;
                        extremeIndex = k;
                        return TradeType.Sell;
                    }
                }

                // ------ FUND -> BUY ------
                double priorLow = Lowest(k - SwingLookback, k - 1);
                double lowK = Bars.LowPrices[k];
                if (lowK < priorLow && lowK <= Bars.LowPrices[i] && lowK <= Bars.LowPrices[i - 1])
                {
                    double legHigh = Highest(k - SwingLookback, k);
                    bool bigMove = legHigh - lowK >= MinLegAtr * atr;
                    bool rsiOk = !UseRsiFilter || Math.Min(_rsi.Result[k], _rsi.Result[k - 1]) <= RsiOversold;
                    bool rejected = (k == i) ? IsBullishRejection(k) : IsBullishConfirmation(i, k);

                    if (bigMove && rsiOk && rejected)
                    {
                        extremePrice = lowK;
                        extremeIndex = k;
                        return TradeType.Buy;
                    }
                }
            }

            return null;
        }

        // Qiri me bisht te gjate lart dhe mbyllje ne pjesen e poshtme
        private bool IsBearishRejection(int k)
        {
            double o = Bars.OpenPrices[k], h = Bars.HighPrices[k], l = Bars.LowPrices[k], c = Bars.ClosePrices[k];
            double range = h - l;
            if (range <= 0) return false;
            double upperWick = h - Math.Max(o, c);
            double closeFromHigh = (h - c) / range * 100.0;
            return upperWick / range * 100.0 >= MinWickPercent && closeFromHigh >= MinClosePercent;
        }

        // Qiri me bisht te gjate poshte dhe mbyllje ne pjesen e siperme
        private bool IsBullishRejection(int k)
        {
            double o = Bars.OpenPrices[k], h = Bars.HighPrices[k], l = Bars.LowPrices[k], c = Bars.ClosePrices[k];
            double range = h - l;
            if (range <= 0) return false;
            double lowerWick = Math.Min(o, c) - l;
            double closeFromLow = (c - l) / range * 100.0;
            return lowerWick / range * 100.0 >= MinWickPercent && closeFromLow >= MinClosePercent;
        }

        // Qiri pas majes mbyllet bearish nen trupin e qirit te majes
        private bool IsBearishConfirmation(int i, int k)
        {
            double bodyLow = Math.Min(Bars.OpenPrices[k], Bars.ClosePrices[k]);
            return Bars.ClosePrices[i] < Bars.OpenPrices[i] && Bars.ClosePrices[i] < bodyLow;
        }

        // Qiri pas fundit mbyllet bullish mbi trupin e qirit te fundit
        private bool IsBullishConfirmation(int i, int k)
        {
            double bodyHigh = Math.Max(Bars.OpenPrices[k], Bars.ClosePrices[k]);
            return Bars.ClosePrices[i] > Bars.OpenPrices[i] && Bars.ClosePrices[i] > bodyHigh;
        }

        private double Highest(int from, int to)
        {
            double max = double.MinValue;
            for (int j = Math.Max(0, from); j <= to; j++)
                max = Math.Max(max, Bars.HighPrices[j]);
            return max;
        }

        private double Lowest(int from, int to)
        {
            double min = double.MaxValue;
            for (int j = Math.Max(0, from); j <= to; j++)
                min = Math.Min(min, Bars.LowPrices[j]);
            return min;
        }

        // ================================================================
        //  Filtrat dhe hapja e trade-it
        // ================================================================
        private bool CanTrade(int i)
        {
            if (_dailyLimitHit)
            {
                Print("Sinjal i injoruar: u arrit humbja max ditore.");
                return false;
            }
            if (_tradesToday >= MaxTradesPerDay)
            {
                Print("Sinjal i injoruar: u arrit numri max i trade-ve sot ({0}).", MaxTradesPerDay);
                return false;
            }
            if (Positions.FindAll(BotLabel, SymbolName).Length > 0)
            {
                Print("Sinjal i injoruar: ka tashme nje pozicion te hapur.");
                return false;
            }
            if (i - _lastSignalBarIndex < CooldownBars)
                return false;

            int hour = Server.Time.Hour;
            bool inSession = StartHourUtc <= EndHourUtc
                ? hour >= StartHourUtc && hour < EndHourUtc
                : hour >= StartHourUtc || hour < EndHourUtc;
            if (!inSession)
            {
                Print("Sinjal i injoruar: jashte orarit te tregtimit ({0}:00 UTC).", hour);
                return false;
            }

            double spreadPips = Symbol.Spread / Symbol.PipSize;
            if (spreadPips > MaxSpreadPips)
            {
                Print("Sinjal i injoruar: spread shume i madh ({0:F1} pips).", spreadPips);
                return false;
            }
            return true;
        }

        private void OpenTrade(TradeType type, double extremePrice, int i)
        {
            double atr = _atr.Result[i];
            double entry = type == TradeType.Buy ? Symbol.Ask : Symbol.Bid;

            double slPrice = type == TradeType.Buy
                ? extremePrice - SlBufferAtr * atr
                : extremePrice + SlBufferAtr * atr;

            double slDistance = Math.Abs(entry - slPrice);
            if (slDistance < MinSlPrice)
                slDistance = MinSlPrice;

            if (slDistance > MaxSlPrice)
            {
                Print("Sinjal i injoruar: SL shume i madh ({0:F2}$ > {1:F2}$).", slDistance, MaxSlPrice);
                return;
            }

            double slPips = slDistance / Symbol.PipSize;
            double tpPips = slPips * RewardRatio;

            double volume = CalculateVolume(slPips);
            if (volume <= 0)
                return;

            string side = type == TradeType.Buy ? "BUY (fund)" : "SELL (maje)";
            var result = ExecuteMarketOrder(type, SymbolName, volume, BotLabel, slPips, tpPips, side);

            if (result.IsSuccessful)
            {
                _tradesToday++;
                _lastSignalBarIndex = i;
                Print("{0} u hap @ {1} | Lot: {2} | SL: {3:F2}$ | TP: {4:F2}$ | Ekstremi: {5}",
                    side, result.Position.EntryPrice, Symbol.VolumeInUnitsToQuantity(volume),
                    slDistance, slDistance * RewardRatio, extremePrice);
            }
            else
            {
                Print("Hapja deshtoi: {0}", result.Error);
            }
        }

        private double CalculateVolume(double slPips)
        {
            if (UseFixedLots)
                return Symbol.NormalizeVolumeInUnits(Symbol.QuantityToVolumeInUnits(FixedLots), RoundingMode.Down);

            double riskMoney = Account.Balance * RiskPercent / 100.0;
            double rawVolume = riskMoney / (slPips * Symbol.PipValue);
            double volume = Symbol.NormalizeVolumeInUnits(rawVolume, RoundingMode.Down);

            if (volume < Symbol.VolumeInUnitsMin)
            {
                if (!AllowMinVolume)
                {
                    Print("Sinjal i injoruar: balanca shume e vogel per rrezikun {0}%.", RiskPercent);
                    return 0;
                }
                Print("Kujdes: volumi i llogaritur eshte nen minimumin, perdoret volumi min.");
                volume = Symbol.VolumeInUnitsMin;
            }
            return Math.Min(volume, Symbol.VolumeInUnitsMax);
        }

        // ================================================================
        //  Menaxhimi i pozicioneve
        // ================================================================
        private void ManageBreakEven()
        {
            if (BreakEvenAtR <= 0)
                return;

            foreach (var pos in Positions.FindAll(BotLabel, SymbolName))
            {
                if (pos.StopLoss == null)
                    continue;

                double sl = pos.StopLoss.Value;
                bool isBuy = pos.TradeType == TradeType.Buy;

                // SL eshte ende ne anen e humbjes -> rreziku fillestar
                double risk = isBuy ? pos.EntryPrice - sl : sl - pos.EntryPrice;
                if (risk <= 0)
                    continue;

                double price = isBuy ? Symbol.Bid : Symbol.Ask;
                double profit = isBuy ? price - pos.EntryPrice : pos.EntryPrice - price;

                if (profit >= risk * BreakEvenAtR)
                {
                    double buffer = Symbol.Spread;
                    double newSl = isBuy ? pos.EntryPrice + buffer : pos.EntryPrice - buffer;
                    var res = pos.ModifyStopLossPrice(Math.Round(newSl, Symbol.Digits));
                    if (res.IsSuccessful)
                        Print("Break-even: SL u zhvendos ne {0} per pozicionin {1}.", newSl, pos.Id);
                }
            }
        }

        private void CheckDailyLoss()
        {
            if (_dailyLimitHit)
                return;
            double lossPercent = (_dayStartBalance - Account.Equity) / _dayStartBalance * 100.0;
            if (lossPercent >= MaxDailyLossPercent)
            {
                _dailyLimitHit = true;
                foreach (var pos in Positions.FindAll(BotLabel, SymbolName))
                    ClosePosition(pos);
                Print("U arrit humbja max ditore ({0:F2}%). Nuk tregtohet me sot.", lossPercent);
            }
        }

        private void OnPositionClosed(PositionClosedEventArgs args)
        {
            var pos = args.Position;
            if (pos.Label != BotLabel || pos.SymbolName != SymbolName)
                return;
            Print("Pozicioni {0} u mbyll | Fitimi neto: {1:F2} {2}", pos.Id, pos.NetProfit, Account.Asset.Name);
        }

        private void ResetDay(DateTime day)
        {
            _currentDay = day;
            _dayStartBalance = Account.Balance;
            _dailyLimitHit = false;
            _tradesToday = History.Count(h => h.Label == BotLabel && h.SymbolName == SymbolName && h.EntryTime.Date == day)
                           + Positions.Count(p => p.Label == BotLabel && p.SymbolName == SymbolName && p.EntryTime.Date == day);
        }

        // ================================================================
        //  Vizatimi i zonave (si katroret roze ne screenshot)
        // ================================================================
        private void DrawZone(TradeType type, int k, double extremePrice)
        {
            double atr = _atr.Result[k];
            DateTime t1 = Bars.OpenTimes[k];
            DateTime t2 = t1.AddMinutes(15 * 6);
            string name = "GS_" + type + "_" + t1.Ticks;

            double y1 = extremePrice;
            double y2 = type == TradeType.Sell ? extremePrice - atr : extremePrice + atr;

            var rect = Chart.DrawRectangle(name, t1, y1, t2, y2, Color.FromArgb(90, 255, 120, 120));
            rect.IsFilled = true;

            var icon = type == TradeType.Sell ? ChartIconType.DownArrow : ChartIconType.UpArrow;
            double iconY = type == TradeType.Sell ? extremePrice + atr * 0.5 : extremePrice - atr * 0.5;
            Chart.DrawIcon(name + "_icon", icon, t1, iconY, Color.Red);
        }

        private static bool IsGoldSymbol(string name)
        {
            string s = name.ToUpperInvariant().Replace("/", "").Replace(".", "");
            return s.StartsWith("XAUUSD") || s == "GOLD";
        }
    }
}
