
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

df = pd.read_csv("C:\\Users\\pl\\Downloads\\System-Automation-PSG-24i433\\Day-2\\Data\\day2_sample.csv")

X = df[["temperature", "pressure", "vibration", "current", "rpm"]]
y = df["state"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

decision_tree = DecisionTreeClassifier(random_state=42)
decision_tree.fit(X_train, y_train)
dt_predictions = decision_tree.predict(X_test)

dt_accuracy = accuracy_score(y_test, dt_predictions)
print(f"Decision Tree Accuracy: {dt_accuracy * 100:.2f}%")


random_forest = RandomForestClassifier(
    n_estimators=200,
    random_state=42
)
random_forest.fit(X_train, y_train)
rf_predictions = random_forest.predict(X_test)

rf_accuracy = accuracy_score(y_test, rf_predictions)
print(f"Random Forest Accuracy: {rf_accuracy * 100:.2f}%")


naive_bayes = make_pipeline(
    StandardScaler(),
    GaussianNB()
)
naive_bayes.fit(X_train, y_train)
nb_predictions = naive_bayes.predict(X_test)

nb_accuracy = accuracy_score(y_test, nb_predictions)
print(f"Naive Bayes Accuracy: {nb_accuracy * 100:.2f}%")
