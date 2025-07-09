import { useParams } from "react-router-dom";

function TimeSeriesWrapper() {
    const { satellite, instrument } = useParams();

    if (!satellite || !instrument) {
        return (
            <div className="p-4">
                <h1 className="text-xl font-bold text-red-600">Missing satellite or instrument info</h1>
            </div>
        );
    }

    return (
        <div className="p-4">
            <h1 className="text-2xl font-bold mb-2">
                {satellite.toUpperCase()} / {instrument.toUpperCase()} Summary Page
            </h1>
            <p>
                This is a placeholder time-series for the instrument <strong>{satellite.toUpperCase()}</strong> / <strong>{instrument}</strong>.
            </p >
        </div >
    );
}

export default TimeSeriesWrapper;
